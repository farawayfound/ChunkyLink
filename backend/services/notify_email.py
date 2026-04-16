# -*- coding: utf-8 -*-
"""Resolve and validate notification email addresses (index, library, etc.)."""
from __future__ import annotations

import re

from backend.database import get_db

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def parse_submitted_notify_email(submitted: str | None) -> str | None:
    """Return normalized email or None. Raises ValueError if non-empty but invalid."""
    cleaned = (submitted or "").strip().lower()
    if not cleaned:
        return None
    if not _EMAIL_RE.match(cleaned):
        raise ValueError("Invalid email address")
    return cleaned


async def resolve_notification_email(user_id: str, submitted: str | None) -> str | None:
    """Decide which email (if any) to use for completion notifications.

    Priority: submitted (validated) → users.email → access_requests.email lookup.
    If submitted is provided, persist it to users.email for future runs.
    Raises ValueError if submitted is non-empty but invalid.
    """
    cleaned = parse_submitted_notify_email(submitted)

    db = await get_db()
    try:
        if cleaned:
            await db.execute("UPDATE users SET email = ? WHERE id = ?", (cleaned, user_id))
            await db.commit()
            return cleaned

        cursor = await db.execute("SELECT email FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row["email"]:
            return row["email"]

        cursor = await db.execute(
            "SELECT ar.email FROM access_requests ar "
            "JOIN sessions s ON s.user_id = ? "
            "JOIN invite_codes ic ON ic.code = ar.invite_code "
            "WHERE ar.status = 'sent' AND ic.created_by = 'system:request-access' "
            "ORDER BY ar.created_at DESC LIMIT 1",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row and row["email"]:
            await db.execute("UPDATE users SET email = ? WHERE id = ?", (row["email"], user_id))
            await db.commit()
            return row["email"]
    finally:
        await db.close()

    return None

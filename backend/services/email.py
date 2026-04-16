# -*- coding: utf-8 -*-
"""Email service for invite codes, index completion, and library notifications."""
from __future__ import annotations

import html
import logging
import smtplib
import ssl
from email.message import EmailMessage

import aiosmtplib

from backend.config import get_settings

log = logging.getLogger(__name__)


def _invite_use_note(max_uses: int) -> str:
    if max_uses == 1:
        return "This code is single-use and expires in 48 hours."
    if max_uses > 1:
        return f"This code can be used up to {max_uses} times and expires in 48 hours."
    return "This code expires in 48 hours."


def _smtp_send_message_sync(msg: EmailMessage) -> bool:
    """Deliver a message using stdlib smtplib (safe from worker / thread-pool contexts)."""
    settings = get_settings()
    if not settings.SMTP_HOST:
        log.warning("email: SMTP not configured — skipping send")
        return False

    host = settings.SMTP_HOST
    port = settings.SMTP_PORT
    user = settings.SMTP_USER or ""
    password = settings.SMTP_PASSWORD or ""
    use_starttls = settings.SMTP_USE_TLS

    ctx = ssl.create_default_context()
    try:
        # Port 465 typically expects implicit TLS (SMTPS), not STARTTLS.
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as smtp:
                smtp.ehlo()
                if use_starttls:
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
        return True
    except Exception:
        log.error("email: SMTP send failed", exc_info=True)
        return False


def _build_index_complete_message(
    to_email: str,
    doc_count: int,
    chunk_count: int,
    insights_generated: bool,
    failed: bool = False,
    error: str | None = None,
) -> EmailMessage:
    settings = get_settings()
    msg = EmailMessage()
    if failed:
        msg["Subject"] = "ChunkyPotato — index build failed"
    else:
        msg["Subject"] = "ChunkyPotato has finished baking your index"
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to_email

    if failed:
        body_text = (
            f"Hi,\n\n"
            f"Unfortunately your index build did not complete successfully.\n\n"
            f"Error: {error or 'unknown'}\n\n"
            f"You can log back in and try again.\n\n"
            f"— ChunkyPotato"
        )
        err_esc = html.escape(error or "unknown error")
        body_html = f"""<html><body style="font-family: -apple-system, sans-serif; color: #e4e6ed; background: #0f1117; padding: 40px;">
        <div style="max-width: 480px; margin: 0 auto; background: #1a1d27; border: 1px solid #2a2e3d; border-radius: 12px; padding: 40px;">
            <h2 style="color: #ef4444; margin-top: 0;">Index build failed</h2>
            <p style="color: #8b8fa3;">Your index build did not complete.</p>
            <pre style="background: #0f1117; border: 1px solid #2a2e3d; border-radius: 8px; padding: 16px; color: #e4e6ed; font-size: 13px; white-space: pre-wrap;">{err_esc}</pre>
            <p style="color: #8b8fa3;">Log back in and try again.</p>
        </div>
        </body></html>"""
    else:
        insights_line = (
            "Insights were generated for each document."
            if insights_generated
            else "Insights generation was skipped for this run."
        )
        body_text = (
            f"Hi,\n\n"
            f"Your ChunkyPotato index has finished baking!\n\n"
            f"  • Documents indexed: {doc_count}\n"
            f"  • Chunks created: {chunk_count}\n"
            f"  • {insights_line}\n\n"
            f"Log back in to start asking questions about your documents.\n\n"
            f"— ChunkyPotato"
        )
        body_html = f"""<html><body style="font-family: -apple-system, sans-serif; color: #e4e6ed; background: #0f1117; padding: 40px;">
        <div style="max-width: 480px; margin: 0 auto; background: #1a1d27; border: 1px solid #2a2e3d; border-radius: 12px; padding: 40px;">
            <h2 style="color: #6366f1; margin-top: 0;">Your index is ready</h2>
            <p style="color: #8b8fa3;">ChunkyPotato has finished baking your index.</p>
            <div style="background: #0f1117; border: 1px solid #2a2e3d; border-radius: 8px; padding: 20px; margin: 24px 0; color: #e4e6ed;">
                <p style="margin: 4px 0;"><strong>Documents indexed:</strong> {doc_count}</p>
                <p style="margin: 4px 0;"><strong>Chunks created:</strong> {chunk_count}</p>
                <p style="margin: 4px 0;">{insights_line}</p>
            </div>
            <p style="color: #8b8fa3;">Log back in to start asking questions about your documents.</p>
        </div>
        </body></html>"""

    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")
    return msg


def send_index_complete_email_sync(
    to_email: str,
    doc_count: int,
    chunk_count: int,
    insights_generated: bool,
    failed: bool = False,
    error: str | None = None,
) -> bool:
    """Notify a user that their index build has finished (sync; use from background threads)."""
    settings = get_settings()
    if not settings.SMTP_HOST:
        log.warning("email: SMTP not configured — skipping index-complete send to %s", to_email)
        return False

    msg = _build_index_complete_message(
        to_email, doc_count, chunk_count, insights_generated, failed=failed, error=error,
    )
    ok = _smtp_send_message_sync(msg)
    if ok:
        log.info("email: index-complete sent to %s (failed=%s)", to_email, failed)
    return ok


def send_library_research_ready_email_sync(
    to_email: str,
    prompt: str,
    job_id: str,
) -> bool:
    """Notify a user that a Library research job is ready for review (sync)."""
    settings = get_settings()
    if not settings.SMTP_HOST:
        log.warning("email: SMTP not configured — skipping library-ready send to %s", to_email)
        return False

    preview = prompt if len(prompt) <= 160 else prompt[:157] + "…"
    preview_esc = html.escape(preview)
    job_esc = html.escape(job_id)

    msg = EmailMessage()
    msg["Subject"] = "ChunkyPotato — your Library research is ready"
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to_email
    msg.set_content(
        f"Hi,\n\n"
        f"Your Library research report is ready for review in ChunkyPotato.\n\n"
        f"Topic:\n{preview}\n\n"
        f"Job ID: {job_id}\n\n"
        f"Open the Library page in your workspace to read and approve the article.\n\n"
        f"— ChunkyPotato"
    )
    msg.add_alternative(
        f"""<html><body style="font-family: -apple-system, sans-serif; color: #e4e6ed; background: #0f1117; padding: 40px;">
        <div style="max-width: 520px; margin: 0 auto; background: #1a1d27; border: 1px solid #2a2e3d; border-radius: 12px; padding: 40px;">
            <h2 style="color: #6366f1; margin-top: 0;">Library research ready</h2>
            <p style="color: #8b8fa3;">Your research report finished and is waiting in <strong>review</strong>.</p>
            <p style="color: #e4e6ed; background: #0f1117; border: 1px solid #2a2e3d; border-radius: 8px; padding: 16px;">{preview_esc}</p>
            <p style="color: #8b8fa3; font-size: 13px;">Job ID: <code style="color: #e4e6ed;">{job_esc}</code></p>
            <p style="color: #8b8fa3;">Open <strong>Library</strong> in your workspace to read sources and approve or reject the import.</p>
        </div>
        </body></html>""",
        subtype="html",
    )

    ok = _smtp_send_message_sync(msg)
    if ok:
        log.info("email: library-ready sent to %s (job=%s)", to_email, job_id)
    return ok


async def send_invite_email(to_email: str, invite_code: str, *, max_uses: int = 1) -> bool:
    """Send an invite code to the given email address. Returns True on success."""
    settings = get_settings()

    if not settings.SMTP_HOST:
        log.warning("email: SMTP not configured — skipping send to %s", to_email)
        return False

    use_note = _invite_use_note(max_uses)
    msg = EmailMessage()
    msg["Subject"] = "Your ChunkyPotato Access Code"
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to_email
    msg.set_content(
        f"Hi there!\n\n"
        f"Here is your access code for ChunkyPotato:\n\n"
        f"    {invite_code}\n\n"
        f"Enter this code on the login page to get started.\n\n"
        f"{use_note}\n\n"
        f"— ChunkyPotato"
    )
    msg.add_alternative(
        f"""<html><body style="font-family: -apple-system, sans-serif; color: #e4e6ed; background: #0f1117; padding: 40px;">
        <div style="max-width: 480px; margin: 0 auto; background: #1a1d27; border: 1px solid #2a2e3d; border-radius: 12px; padding: 40px;">
            <h2 style="color: #6366f1; margin-top: 0;">Your Access Code</h2>
            <p style="color: #8b8fa3;">Here is your access code for ChunkyPotato:</p>
            <div style="background: #0f1117; border: 1px solid #2a2e3d; border-radius: 8px; padding: 20px; text-align: center; margin: 24px 0;">
                <code style="font-size: 28px; letter-spacing: 4px; color: #e4e6ed; font-family: 'JetBrains Mono', monospace;">{invite_code}</code>
            </div>
            <p style="color: #8b8fa3;">Enter this code on the login page to get started.</p>
            <p style="color: #8b8fa3; font-size: 13px;">{use_note}</p>
        </div>
        </body></html>""",
        subtype="html",
    )

    try:
        if settings.SMTP_PORT == 465:
            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER or None,
                password=settings.SMTP_PASSWORD or None,
                use_tls=True,
            )
        else:
            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER or None,
                password=settings.SMTP_PASSWORD or None,
                start_tls=settings.SMTP_USE_TLS,
            )
        log.info("email: invite code sent to %s", to_email)
        return True
    except Exception:
        log.error("email: failed to send to %s", to_email, exc_info=True)
        return False


async def send_index_complete_email(
    to_email: str,
    doc_count: int,
    chunk_count: int,
    insights_generated: bool,
    failed: bool = False,
    error: str | None = None,
) -> bool:
    """Async wrapper (e.g. tests); production index path uses send_index_complete_email_sync."""
    import asyncio

    return await asyncio.to_thread(
        send_index_complete_email_sync,
        to_email,
        doc_count,
        chunk_count,
        insights_generated,
        failed,
        error,
    )

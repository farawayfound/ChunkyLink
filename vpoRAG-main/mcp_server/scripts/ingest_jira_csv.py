# -*- coding: utf-8 -*-
"""
Ingest DPSTRIAGE CSV export into MySQL — upserts only when incoming Updated > stored Updated.
CSV source: /srv/samba/share/dpstriageCSV/
Table: jira_db.dpstriage
"""
import csv, os, sys, logging
from datetime import datetime
from pathlib import Path

try:
    import pymysql
except ImportError:
    raise SystemExit("pip install pymysql")

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
try:
    from logger import log_csv_ingest
except ImportError:
    def log_csv_ingest(*a, **kw): pass

DB_CONFIG = {
    'host':     config.MYSQL_HOST,
    'port':     config.MYSQL_PORT,
    'user':     config.MYSQL_USER,
    'password': config.MYSQL_PASS,
    'database': config.MYSQL_DB,
    'charset':  'utf8mb4',
}

CSV_DIR  = config.DPSTRIAGE_CSV_DIR + '/'
LOG_FILE = str(Path(__file__).parent.parent.parent / 'JSON' / 'logs' / 'ingest_dpstriage.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

# Actual CSV columns → DB columns
FIELD_MAP = {
    'Key':                      'Issue key',
    'Issue_id':                 'Issue id',
    'Status':                   'Status',
    'Assignee':                 'Assignee',
    'Summary':                  'Summary',
    'Description':              'Description',
    'Created':                  'Created',
    'Updated':                  'Updated',
    'Priority':                 'Priority',
    'Root_Cause':               'Custom field (Root Cause)',
    'Resolution_Category':      'Custom field (Resolution Category)',
    'Requesting_Organization':  'Custom field (Requesting Organization)',
    'Environment_HE_Controller':'Custom field (Environment HE/Controller)',
    'Customer_Type':            'Custom field (Customer type)',
    'Customer_Impact':          'Custom field (Customer Impact)',
    'Last_Comment':             'Custom field (Last Comment)',
    'Resolution_Mitigation':    'Custom field (Resolution / Mitigation Solution)',
    'Vertical':                 'Custom field (Vertical)',
    'Labels':                   'Labels',
}

# These columns are not in every export — default to empty string if absent
OPTIONAL_CSV_COLS = {
    'Description',
    'Custom field (Root Cause)',
    'Custom field (Resolution / Mitigation Solution)',
}

DATE_FORMATS = (
    '%b %d, %Y %I:%M %p',   # Mar 12, 2026 1:42 AM
    '%b %d, %Y %H:%M',       # Mar 12, 2026 13:42
    '%m/%d/%Y %H:%M',
    '%m/%d/%Y %H:%M:%S',
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%d',
)

def parse_date(s):
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None

def get_latest_csv():
    files = list(Path(CSV_DIR).glob('*.csv'))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {CSV_DIR}")
    return max(files, key=os.path.getmtime)

def ingest():
    csv_file = get_latest_csv()
    logging.info(f"Processing DPSTRIAGE: {csv_file.name}")

    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()

    inserted = updated = skipped = 0

    with open(csv_file, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            key = row.get('Issue key', '').strip()
            if not key:
                continue

            incoming_updated = parse_date(row.get('Updated', ''))

            # Only update if incoming Updated is strictly newer than stored
            cur.execute("SELECT `Updated` FROM dpstriage WHERE `Key` = %s", (key,))
            existing = cur.fetchone()

            if existing is not None:
                stored_updated = existing[0]  # already a datetime from MySQL
                if not incoming_updated or (stored_updated and incoming_updated <= stored_updated):
                    skipped += 1
                    continue

            vals = (
                key,
                row.get('Issue id', '').strip(),
                row.get('Status', '').strip(),
                row.get('Assignee', '').strip(),
                row.get('Summary', '').strip(),
                row.get('Description', '').strip() if 'Description' in row else '',
                parse_date(row.get('Created', '')),
                incoming_updated,
                row.get('Priority', '').strip(),
                '',  # Platform_Affected — not in this export
                row.get('Custom field (Root Cause)', '').strip() if 'Custom field (Root Cause)' in row else '',
                row.get('Custom field (Resolution Category)', '').strip(),
                row.get('Custom field (Requesting Organization)', '').strip(),
                row.get('Custom field (Environment HE/Controller)', '').strip(),
                row.get('Custom field (Customer type)', '').strip(),
                row.get('Custom field (Customer Impact)', '').strip(),
                row.get('Custom field (Last Comment)', '').strip(),
                row.get('Custom field (Resolution / Mitigation Solution)', '').strip() if 'Custom field (Resolution / Mitigation Solution)' in row else '',
                row.get('Custom field (Vertical)', '').strip(),
                row.get('Labels', '').strip(),
            )

            try:
                if existing is None:
                    cur.execute("""
                        INSERT INTO dpstriage
                        (`Key`,Issue_id,Status,Assignee,Summary,Description,Created,Updated,
                         Priority,Platform_Affected,Root_Cause,Resolution_Category,
                         Requesting_Organization,Environment_HE_Controller,Customer_Type,
                         Customer_Impact,Last_Comment,Resolution_Mitigation,Vertical,Labels)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, vals)
                    inserted += 1
                else:
                    cur.execute("""
                        UPDATE dpstriage SET
                        Status=%s,Assignee=%s,Summary=%s,Description=%s,Updated=%s,Priority=%s,
                        Root_Cause=%s,Resolution_Category=%s,Requesting_Organization=%s,
                        Environment_HE_Controller=%s,Customer_Type=%s,Customer_Impact=%s,
                        Last_Comment=%s,Resolution_Mitigation=%s,Vertical=%s,Labels=%s
                        WHERE `Key`=%s
                    """, (vals[2],vals[3],vals[4],vals[5],vals[7],vals[8],
                          vals[10],vals[11],vals[12],vals[13],vals[14],vals[15],
                          vals[16],vals[17],vals[18],vals[19], key))
                    updated += 1
            except Exception as e:
                logging.warning(f"Row {key}: {e}")
                skipped += 1
                continue

            if (inserted + updated) % 200 == 0:
                conn.commit()
                logging.info(f"  ...{inserted + updated} processed")

    conn.commit()

    # Log import record
    cur.execute("""
        INSERT INTO csv_imports (filename, ticket_type, imported_at, rows_inserted, rows_updated)
        VALUES (%s, 'dpstriage', %s, %s, %s)
    """, (csv_file.name, datetime.utcnow(), inserted, updated))
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM dpstriage")
    total_rows = cur.fetchone()[0]
    cur.close()
    conn.close()

    logging.info(f"DPSTRIAGE done — inserted={inserted} updated={updated} skipped={skipped}")
    log_csv_ingest('dpstriage', csv_file.name, 'pass',
                   rows_inserted=inserted, rows_updated=updated, total_rows=total_rows)

if __name__ == '__main__':
    try:
        ingest()
    except Exception as e:
        logging.exception(f"Fatal: {e}")
        log_csv_ingest('dpstriage', '', 'fail', error=str(e))
        sys.exit(1)

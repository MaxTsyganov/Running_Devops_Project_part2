"""
=============================================================
  TIER 3 — Background Worker
=============================================================
Responsibilities:
  • Poll PostgreSQL (RDS) every 30 seconds for 'pending' items
  • Process each item (simulate work, then mark as 'done')
  • Send an SNS email notification for each item it processes

This process runs independently on its OWN EC2 server.
It DOES NOT call the backend API — it connects directly to
the shared RDS database, just like the backend does.

Run (foreground) : python worker.py
Run (background) : see worker.service (systemd unit file)
=============================================================
"""

import os
import time
import logging
from datetime import datetime

import boto3
import psycopg2
import psycopg2.extras
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# ── Load .env file (dev convenience) ─────────────────────────────────────────
load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("worker")

# ─────────────────────────────────────────────────────────────────────────────
#   Configuration  (mirrors backend .env.template)
# ─────────────────────────────────────────────────────────────────────────────

# --- PostgreSQL / RDS ---------------------------------------------------------
DB_HOST = os.environ.get("DB_HOST",     "localhost")
DB_PORT = os.environ.get("DB_PORT",     "5432")
DB_NAME = os.environ.get("DB_NAME",     "appdb")
DB_USER = os.environ.get("DB_USER",     "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "changeme")

# --- AWS (leave blank on EC2 with IAM Role) -----------------------------------
AWS_REGION = os.environ.get("AWS_REGION",            "us-east-1")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN",         "")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID",     "") or None
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "") or None

# How often (seconds) the worker wakes up to check for pending items
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))


# =============================================================================
#   Helpers
# =============================================================================

def get_db_connection():
    """Open a new psycopg2 connection to RDS."""
    return psycopg2.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=5,
    )


def publish_sns(subject: str, message: str):
    """Send a notification email via SNS to all topic subscribers."""
    if not SNS_TOPIC_ARN:
        logger.warning("SNS_TOPIC_ARN not set — notification skipped.")
        return
    try:
        sns = boto3.client(
            "sns",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )
        resp = sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message,
        )
        logger.info(f"SNS notification sent — MessageId: {resp['MessageId']}")
    except ClientError:
        logger.exception("SNS publish failed")


# =============================================================================
#   Core Worker Logic
# =============================================================================

def fetch_pending_items(conn) -> list[dict]:
    """
    Read all items with status='pending' from the database.
    This is the READ operation on RDS.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT id, name, description, created_at
            FROM   items
            WHERE  status = 'pending'
            ORDER  BY created_at ASC;
        """)
        return [dict(row) for row in cur.fetchall()]


def mark_item_done(conn, item_id: int):
    """
    Update a single item's status to 'done' and stamp the processed_at time.
    This is the WRITE operation on RDS (from the worker side).
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE items
            SET    status       = 'done',
                   processed_at = CURRENT_TIMESTAMP
            WHERE  id = %s;
        """, (item_id,))
    conn.commit()


def process_item(item: dict):
    """
    Simulate business logic for one item.
    Replace this with real work (e.g. resize images, run ML inference, etc.)
    """
    logger.info(f"Processing item id={item['id']} name='{item['name']}' …")

    # ── Simulated processing delay (replace with real work) ──────────────────
    time.sleep(0.5)

    logger.info(f"Item id={item['id']} processed successfully.")


def run_one_cycle():
    """
    One full poll-and-process cycle:
      1. Connect to RDS
      2. Fetch all pending items
      3. Process each item
      4. Mark each item as 'done'
      5. Send a single SNS summary email if anything was processed
    """
    try:
        conn = get_db_connection()
    except Exception:
        logger.exception("Cannot connect to database — will retry next cycle")
        return

    try:
        pending = fetch_pending_items(conn)

        if not pending:
            logger.info("No pending items found.")
            conn.close()
            return

        logger.info(f"Found {len(pending)} pending item(s) — processing …")
        processed_names = []

        for item in pending:
            try:
                process_item(item)
                mark_item_done(conn, item["id"])
                processed_names.append(item["name"])
                logger.info(f"Item id={item['id']} marked as done.")
            except Exception:
                logger.exception(f"Failed to process item id={item['id']}")
                # Continue with the remaining items even if one fails

        # ── Send a single SNS batch-summary email ─────────────────────────────
        if processed_names:
            count = len(processed_names)
            names_list = "\n".join(f"  • {n}" for n in processed_names)
            publish_sns(
                subject=f"[Worker] {count} item(s) processed successfully",
                message=(
                    f"The background worker finished processing {count} item(s).\n\n"
                    f"Processed items:\n{names_list}\n\n"
                    f"Completed at: {datetime.utcnow().isoformat()}Z\n"
                ),
            )

    finally:
        conn.close()


# =============================================================================
#   Main Loop
# =============================================================================

def main():
    logger.info("=" * 60)
    logger.info("  Background Worker started")
    logger.info(f"  Database : {DB_HOST}:{DB_PORT}/{DB_NAME}")
    logger.info(f"  Poll interval : {POLL_INTERVAL_SECONDS}s")
    logger.info("=" * 60)

    while True:
        logger.info("─── Starting new poll cycle ───────────────────────────")
        run_one_cycle()
        logger.info(f"Cycle complete. Sleeping {POLL_INTERVAL_SECONDS}s …\n")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

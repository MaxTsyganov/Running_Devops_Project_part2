"""
Tier 3: Background Worker
This script runs independently to check the database for new tasks.
It processes pending items and sends an email when they are finished.
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

# Load environment variables from the .env file
load_dotenv()

# Configure logging to print messages to the console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("worker")

# Database configuration pulled from environment variables
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "appdb")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "changeme")

# AWS configuration pulled from environment variables
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "") or None
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "") or None

# Set how often the worker checks the database (in seconds)
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))


def get_db_connection():
    """Create a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=5,
    )


def publish_sns(subject: str, message: str):
    """Send an email notification using AWS SNS."""
    if not SNS_TOPIC_ARN:
        logger.warning("SNS topic is missing. Notification skipped.")
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
        logger.info(
            f"Notification sent successfully. Message ID: {resp['MessageId']}")
    except ClientError:
        logger.exception("Failed to send notification")


def fetch_pending_items(conn) -> list[dict]:
    """Find all items in the database that are marked as 'pending'."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT id, name, description, created_at
            FROM   items
            WHERE  status = 'pending'
            ORDER  BY created_at ASC;
        """)
        return [dict(row) for row in cur.fetchall()]


def mark_item_done(conn, item_id: int):
    """Update an item's status in the database to 'done'."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE items
            SET    status       = 'done',
                   processed_at = CURRENT_TIMESTAMP
            WHERE  id = %s;
        """, (item_id,))
    conn.commit()


def process_item(item: dict):
    """Simulate working on a task by pausing for half a second."""
    logger.info(f"Processing item ID {item['id']} named '{item['name']}'...")
    time.sleep(0.5)
    logger.info(f"Item ID {item['id']} processed successfully.")


def run_one_cycle():
    """Check the database, process any pending items, and send an alert."""
    try:
        conn = get_db_connection()
    except Exception:
        logger.exception("Cannot connect to the database. Will retry later.")
        return

    try:
        pending = fetch_pending_items(conn)

        if not pending:
            logger.info("No pending items found.")
            conn.close()
            return

        logger.info(
            f"Found {len(pending)} pending item(s). Starting processing...")
        processed_names = []

        for item in pending:
            try:
                process_item(item)
                mark_item_done(conn, item["id"])
                processed_names.append(item["name"])
                logger.info(f"Item ID {item['id']} marked as done.")
            except Exception:
                logger.exception(f"Failed to process item ID {item['id']}")

        # Send a summary email if any items were processed
        if processed_names:
            count = len(processed_names)
            names_list = "\n".join(f"  - {n}" for n in processed_names)
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


def main():
    """Start the infinite loop to keep the worker running."""
    logger.info("Background Worker started.")
    logger.info(f"Database target: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    logger.info(f"Checking every {POLL_INTERVAL_SECONDS} seconds.")

    while True:
        logger.info("Starting a new check cycle...")
        run_one_cycle()
        logger.info(
            f"Cycle complete. Waiting {POLL_INTERVAL_SECONDS} seconds...\n")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

"""
=============================================================
  TIER 2 — Python Backend API  (Flask)
=============================================================
Responsibilities:
  • CRUD operations on PostgreSQL (AWS RDS)
  • File uploads to AWS S3
  • Email notifications via AWS SNS

Listens on  :  0.0.0.0:5000
Nginx proxy  :  /api/* requests are forwarded here from the
                frontend server.

Run (dev)    :  python app.py
Run (prod)   :  gunicorn -w 4 -b 0.0.0.0:5000 app:app
=============================================================
"""

import os
import logging
from datetime import datetime

import boto3
import psycopg2
import psycopg2.extras
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

# ── Load .env file (dev convenience; in prod use real env vars) ──────────────
load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("backend")

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
# Allow the Nginx frontend server to call this API across origins.
CORS(app)

# ─────────────────────────────────────────────────────────────────────────────
#   Configuration  (all values come from environment variables)
# ─────────────────────────────────────────────────────────────────────────────

# --- PostgreSQL / RDS ---------------------------------------------------------
DB_HOST     = os.environ.get("DB_HOST",     "localhost")
DB_PORT     = os.environ.get("DB_PORT",     "5432")
DB_NAME     = os.environ.get("DB_NAME",     "appdb")
DB_USER     = os.environ.get("DB_USER",     "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "changeme")

# --- AWS (leave blank on EC2 — IAM Role supplies credentials automatically) --
AWS_REGION            = os.environ.get("AWS_REGION",            "us-east-1")
S3_BUCKET_NAME        = os.environ.get("S3_BUCKET_NAME",        "")
SNS_TOPIC_ARN         = os.environ.get("SNS_TOPIC_ARN",         "")
AWS_ACCESS_KEY_ID     = os.environ.get("AWS_ACCESS_KEY_ID",     "") or None
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "") or None


# =============================================================================
#   Helpers — Database
# =============================================================================

def get_db_connection():
    """Open and return a new psycopg2 connection to the RDS instance."""
    return psycopg2.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=5,
    )


def init_db():
    """
    Create application tables if they don't exist yet.
    Called once at startup so the app is self-bootstrapping.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # items — the main data model
            cur.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id           SERIAL       PRIMARY KEY,
                    name         VARCHAR(255) NOT NULL,
                    description  TEXT         DEFAULT '',
                    status       VARCHAR(50)  DEFAULT 'pending',
                    created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                );
            """)
            # uploads — track every S3 file that was uploaded
            cur.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    id         SERIAL       PRIMARY KEY,
                    filename   VARCHAR(255) NOT NULL,
                    s3_key     VARCHAR(500) NOT NULL,
                    created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
                );
            """)
        conn.commit()
        logger.info("Database tables initialised.")
    except Exception:
        conn.rollback()
        logger.exception("DB initialisation failed")
        raise
    finally:
        conn.close()


# =============================================================================
#   Helpers — AWS
# =============================================================================

def _aws_kwargs():
    """
    Return boto3 credential kwargs.
    On EC2 with an IAM Role these are empty — boto3 picks up the role
    automatically.  For local dev you can put real keys in .env.
    """
    return dict(
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def publish_sns(subject: str, message: str):
    """
    Publish a plain-text message to the SNS topic.
    Any email address subscribed to the topic will receive this.
    """
    if not SNS_TOPIC_ARN:
        logger.warning("SNS_TOPIC_ARN not set — notification skipped.")
        return
    try:
        sns = boto3.client("sns", **_aws_kwargs())
        resp = sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,   # shown as email subject
            Message=message,   # shown as email body
        )
        logger.info(f"SNS published — MessageId: {resp['MessageId']}")
    except ClientError:
        logger.exception("SNS publish failed")  # log but don't crash the API


def _row_to_dict(row: dict) -> dict:
    """Convert psycopg2 RealDictRow to a JSON-serialisable plain dict."""
    out = {}
    for k, v in row.items():
        out[k] = v.isoformat() if isinstance(v, datetime) else v
    return out


# =============================================================================
#   Routes
# =============================================================================

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    """
    GET /api/health
    Quick liveness + database-reachability check.
    Load balancer / Nginx can poll this endpoint.
    """
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({"status": "ok", "db": "reachable"}), 200
    except Exception as exc:
        return jsonify({"status": "error", "detail": str(exc)}), 503


# ── Items (RDS read + write) ──────────────────────────────────────────────────

@app.get("/api/items")
def list_items():
    """
    GET /api/items
    READ from RDS — returns all items ordered newest-first.
    """
    try:
        conn = get_db_connection()
        # RealDictCursor gives us column-name keys instead of positional indices
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM items ORDER BY created_at DESC;")
            rows = cur.fetchall()
        conn.close()
        return jsonify({"items": [_row_to_dict(r) for r in rows]}), 200
    except Exception as exc:
        logger.exception("GET /api/items failed")
        return jsonify({"error": str(exc)}), 500


@app.post("/api/items")
def create_item():
    """
    POST /api/items   { "name": "...", "description": "..." }
    WRITE to RDS — inserts a new item with status='pending',
    then fires an SNS email notification.
    """
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "'name' is required"}), 400

    description = (body.get("description") or "").strip()

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO items (name, description)
                VALUES (%s, %s)
                RETURNING id, status, created_at;
                """,
                (name, description),
            )
            row_id, status, created_at = cur.fetchone()
        conn.commit()
        conn.close()
        logger.info(f"Item created — id={row_id} name='{name}'")
    except Exception as exc:
        logger.exception("POST /api/items DB write failed")
        return jsonify({"error": str(exc)}), 500

    # Fire-and-forget SNS notification
    publish_sns(
        subject=f"[App] New item created: {name}",
        message=(
            f"A new item was added to the database.\n\n"
            f"  ID          : {row_id}\n"
            f"  Name        : {name}\n"
            f"  Description : {description}\n"
            f"  Status      : {status}\n"
            f"  Created at  : {created_at.isoformat()}\n"
        ),
    )

    return jsonify({
        "id":          row_id,
        "name":        name,
        "description": description,
        "status":      status,
        "created_at":  created_at.isoformat(),
    }), 201


# ── File upload (S3) ──────────────────────────────────────────────────────────

@app.post("/api/upload")
def upload_file():
    """
    POST /api/upload   (multipart/form-data, field: 'file')
    Uploads the file to S3, records it in RDS, then sends an SNS notification.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file field in request"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "File has no filename"}), 400

    if not S3_BUCKET_NAME:
        return jsonify({"error": "S3_BUCKET_NAME not configured on server"}), 500

    # Prefix with timestamp to make every key unique
    ts     = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    s3_key = f"uploads/{ts}_{f.filename}"

    # ── Step 1: Upload to S3 ─────────────────────────────────────────────────
    try:
        s3 = boto3.client("s3", **_aws_kwargs())
        s3.upload_fileobj(
            f,
            S3_BUCKET_NAME,
            s3_key,
            ExtraArgs={"ContentType": f.content_type or "application/octet-stream"},
        )
        logger.info(f"S3 upload OK — s3://{S3_BUCKET_NAME}/{s3_key}")
    except ClientError:
        logger.exception("S3 upload failed")
        return jsonify({"error": "S3 upload failed"}), 500

    # ── Step 2: Record upload in RDS ─────────────────────────────────────────
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO uploads (filename, s3_key) VALUES (%s, %s) RETURNING id;",
                (f.filename, s3_key),
            )
            upload_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.exception("Upload DB record failed")
        return jsonify({"error": str(exc)}), 500

    s3_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"

    # ── Step 3: SNS notification ─────────────────────────────────────────────
    publish_sns(
        subject=f"[App] New file uploaded: {f.filename}",
        message=(
            f"A file was uploaded to S3.\n\n"
            f"  Upload ID   : {upload_id}\n"
            f"  Filename    : {f.filename}\n"
            f"  S3 location : s3://{S3_BUCKET_NAME}/{s3_key}\n"
            f"  URL         : {s3_url}\n"
            f"  Uploaded at : {datetime.utcnow().isoformat()}Z\n"
        ),
    )

    return jsonify({
        "id":       upload_id,
        "filename": f.filename,
        "s3_key":   s3_key,
        "s3_url":   s3_url,
    }), 201


# ── Uploads list ──────────────────────────────────────────────────────────────

@app.get("/api/uploads")
def list_uploads():
    """
    GET /api/uploads
    Return all previously uploaded file records from RDS.
    """
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM uploads ORDER BY created_at DESC;")
            rows = cur.fetchall()
        conn.close()
        return jsonify({"uploads": [_row_to_dict(r) for r in rows]}), 200
    except Exception as exc:
        logger.exception("GET /api/uploads failed")
        return jsonify({"error": str(exc)}), 500


# =============================================================================
#   Entry Point
# =============================================================================

if __name__ == "__main__":
    logger.info("Bootstrapping database tables …")
    init_db()
    logger.info("Starting Flask dev server on 0.0.0.0:5000 …")
    # debug=False in prod — use gunicorn instead
    app.run(host="0.0.0.0", port=5000, debug=False)

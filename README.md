# 3-Tier AWS Application — DevOps Deployment Guide

A deliberately simple web application built to demonstrate a **manual, hands-on AWS deployment** across three separate EC2 servers.

---

## Architecture Overview

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                        AWS Cloud (VPC)                          │
  │                                                                 │
  │  ┌──────────────┐   HTTP /api/*   ┌──────────────────────────┐ │
  │  │   Server 1   │ ──────────────► │       Server 2           │ │
  │  │              │                 │                          │ │
  │  │  Nginx       │                 │   Python Flask API       │ │
  │  │  (Frontend)  │ ◄────────────── │   (Backend)  :5000       │ │
  │  │  :80         │   JSON response │                          │ │
  │  └──────────────┘                 └──────────┬───────────────┘ │
  │        ▲                                     │                 │
  │        │ Browser                             │ psycopg2        │
  │        │ (port 80)                           ▼                 │
  │                                   ┌──────────────────────────┐ │
  │  ┌──────────────┐                 │   AWS RDS                │ │
  │  │   Server 3   │ ──psycopg2───►  │   PostgreSQL :5432       │ │
  │  │              │                 └──────────────────────────┘ │
  │  │  Python      │                                              │
  │  │  Worker      │ ──boto3 SNS──►  AWS SNS (email to you)       │
  │  │  (polls DB)  │                                              │
  │  └──────────────┘                 ┌──────────────────────────┐ │
  │                                   │   AWS S3                 │ │
  │  Server 2 ──boto3 S3 ──────────►  │   (file storage)         │ │
  │  Server 2 ──boto3 SNS ─────────►  AWS SNS (email to you)       │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘
```

### How the tiers communicate

| From | To | Method |
|---|---|---|
| Browser | Nginx (Server 1) | HTTP port 80 |
| Nginx (Server 1) | Flask API (Server 2) | HTTP reverse proxy → port 5000 |
| Flask API (Server 2) | RDS PostgreSQL | psycopg2 TCP → port 5432 |
| Flask API (Server 2) | S3 | boto3 HTTPS |
| Flask API (Server 2) | SNS | boto3 HTTPS |
| Worker (Server 3) | RDS PostgreSQL | psycopg2 TCP → port 5432 (direct, no API hop) |
| Worker (Server 3) | SNS | boto3 HTTPS |

---

## Project File Structure

```
Running_Devops_Project_part2/
│
├── frontend/
│   ├── index.html        ← Single-page app (HTML + vanilla JS)
│   └── nginx.conf        ← Nginx reverse-proxy config
│
├── backend/
│   ├── app.py            ← Flask API (RDS reads/writes, S3 upload, SNS)
│   ├── requirements.txt
│   ├── .env.template     ← Copy to .env and fill in values
│   └── backend.service   ← systemd unit (runs gunicorn on boot)
│
└── worker/
    ├── worker.py         ← Background worker (polls DB, sends SNS)
    ├── requirements.txt
    ├── .env.template
    └── worker.service    ← systemd unit (runs worker on boot)
```

---

## Part 1 — AWS Prerequisites

Do these once before touching any EC2 instance.

### 1.1 Create an RDS PostgreSQL instance

1. Go to **RDS → Create database**
2. Engine: **PostgreSQL**, Version: 15.x
3. Template: **Free tier** (for learning)
4. DB instance identifier: `appdb-instance`
5. Master username: `postgres`  |  Master password: (save this!)
6. **VPC**: Same VPC as your EC2 instances
7. **Public access**: No (keep it private inside the VPC)
8. **VPC security group**: Create new → name it `rds-sg`
9. Note the **Endpoint** after it's created (looks like `appdb-instance.xxxxx.us-east-1.rds.amazonaws.com`)

**RDS Security Group rule** (after EC2 instances are created):
- Type: PostgreSQL | Port: 5432 | Source: Security group of Backend EC2 **and** Worker EC2

### 1.2 Create an S3 bucket

1. Go to **S3 → Create bucket**
2. Name: `your-app-uploads-YYYYMMDD` (must be globally unique)
3. Region: Same as EC2
4. Block all public access: **On** (leave default)
5. Note the bucket name

### 1.3 Create an SNS Topic

1. Go to **SNS → Topics → Create topic**
2. Type: **Standard**
3. Name: `app-notifications`
4. After creation, note the **Topic ARN** (looks like `arn:aws:sns:us-east-1:123456789012:app-notifications`)

**Subscribe your email:**
1. Click the topic → **Create subscription**
2. Protocol: **Email**
3. Endpoint: your email address
4. Check your inbox → click the confirmation link SNS sends

### 1.4 Create an IAM Role for EC2 (Recommended)

Using an IAM Role is **more secure** than putting access keys in .env files.

1. Go to **IAM → Roles → Create role**
2. Trusted entity: **EC2**
3. Attach these managed policies:
   - `AmazonS3FullAccess` (or a custom policy scoped to your bucket)
   - `AmazonSNSFullAccess` (or scoped to your topic)
4. Name: `ec2-app-role`
5. Attach this role to **both** your Backend and Worker EC2 instances
   (Instance → Actions → Security → Modify IAM Role)

---

## Part 2 — Launch Three EC2 Instances

Launch **three separate** EC2 instances (one per tier). Use:
- AMI: **Amazon Linux 2023** (or Ubuntu 22.04)
- Instance type: **t2.micro** (Free Tier)
- Same VPC, different roles

### Security Groups

| Instance | Inbound Rules |
|---|---|
| Server 1 (Frontend / Nginx) | TCP 80 from `0.0.0.0/0` (public web traffic) |
| Server 2 (Backend / Flask) | TCP 5000 from **Security Group of Server 1 only** |
| Server 3 (Worker) | No inbound needed (it only makes outbound connections) |

> **Key principle:** The backend is never directly reachable from the internet — only Nginx can call it.

---

## Part 3 — Deploy the Backend (Server 2)

SSH into **Server 2**.

```bash
# 1. Install dependencies
sudo dnf update -y
sudo dnf install -y python3.11 python3.11-pip git

# 2. Copy project files to the server
# Option A: git clone (if you push to GitHub)
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git /home/ec2-user/app
# Option B: scp from your local machine
# scp -r backend/ ec2-user@SERVER2_IP:/home/ec2-user/app/

# 3. Create Python virtual environment
cd /home/ec2-user/app/backend
python3.11 -m venv venv
source venv/bin/activate

# 4. Install Python packages
pip install -r requirements.txt

# 5. Configure environment variables
cp .env.template .env
nano .env
# Fill in: DB_HOST, DB_NAME, DB_USER, DB_PASSWORD
#          S3_BUCKET_NAME, SNS_TOPIC_ARN, AWS_REGION
# If using IAM Role (recommended): leave AWS_ACCESS_KEY_ID blank

# 6. Test that it works
python app.py
# You should see: "Starting Flask dev server on 0.0.0.0:5000"
# Test: curl http://localhost:5000/api/health
# Press Ctrl+C when done

# 7. Install as a systemd service (runs on boot)
sudo cp backend.service /etc/systemd/system/backend.service
sudo systemctl daemon-reload
sudo systemctl enable backend
sudo systemctl start backend
sudo systemctl status backend
```

**Verify the backend is working:**
```bash
# From Server 2 itself:
curl http://localhost:5000/api/health
# Expected: {"status": "ok", "db": "reachable"}

curl http://localhost:5000/api/items
# Expected: {"items": []}
```

---

## Part 4 — Deploy the Worker (Server 3)

SSH into **Server 3**.

```bash
# 1. Install Python
sudo dnf update -y
sudo dnf install -y python3.11 python3.11-pip git

# 2. Copy worker files
# scp -r worker/ ec2-user@SERVER3_IP:/home/ec2-user/app/
cd /home/ec2-user/app/worker

# 3. Virtual environment + packages
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Configure .env
cp .env.template .env
nano .env
# Fill in the same DB_* values as the backend
# Fill in SNS_TOPIC_ARN and AWS_REGION

# 5. Test it runs
python worker.py
# You should see the worker start polling every 30 seconds
# Press Ctrl+C when done

# 6. Install as a systemd service
sudo cp worker.service /etc/systemd/system/worker.service
sudo systemctl daemon-reload
sudo systemctl enable worker
sudo systemctl start worker
sudo systemctl status worker

# View live logs:
journalctl -u worker -f
```

---

## Part 5 — Deploy the Frontend (Server 1)

SSH into **Server 1**.

```bash
# 1. Install Nginx
sudo dnf update -y
sudo dnf install -y nginx

# 2. Edit nginx.conf — set the backend IP
# IMPORTANT: Replace BACKEND_SERVER_IP with Server 2's PRIVATE IP address
nano /home/ec2-user/app/frontend/nginx.conf
# Change this line:
#   proxy_pass  http://BACKEND_SERVER_IP:5000;
# To (example):
#   proxy_pass  http://10.0.1.55:5000;

# 3. Install config and HTML
sudo cp /home/ec2-user/app/frontend/nginx.conf /etc/nginx/conf.d/app.conf
sudo cp /home/ec2-user/app/frontend/index.html /usr/share/nginx/html/index.html

# 4. Remove the default Nginx page
sudo rm -f /etc/nginx/conf.d/default.conf

# 5. Test config and start Nginx
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl start nginx
sudo systemctl status nginx
```

**Verify:** Open your browser → `http://SERVER1_PUBLIC_IP`

You should see the app UI. The green dot in the header means the API is reachable.

---

## Part 6 — End-to-End Test

1. **Open** `http://SERVER1_PUBLIC_IP` in your browser
2. **Create an item** — type a name → click "Add Item"
   - Item appears in the list below (status: `pending`)
   - You receive an email via SNS: "New item created"
3. **Upload a file** — choose any file → click "Upload to S3"
   - Success message with the S3 key
   - You receive an email via SNS: "New file uploaded"
4. **Wait ~30 seconds** for the worker to run
   - Click Refresh — the item's status changes from `pending` → `done`
   - You receive a batch email from the worker: "Items processed"

---

## Environment Variables Reference

| Variable | Used by | Description |
|---|---|---|
| `DB_HOST` | backend, worker | RDS endpoint URL |
| `DB_PORT` | backend, worker | PostgreSQL port (default 5432) |
| `DB_NAME` | backend, worker | Database name |
| `DB_USER` | backend, worker | Database username |
| `DB_PASSWORD` | backend, worker | Database password |
| `AWS_REGION` | backend, worker | e.g. `us-east-1` |
| `S3_BUCKET_NAME` | backend | Name of your S3 bucket |
| `SNS_TOPIC_ARN` | backend, worker | Full SNS Topic ARN |
| `AWS_ACCESS_KEY_ID` | backend, worker | Leave blank if using IAM Role |
| `AWS_SECRET_ACCESS_KEY` | backend, worker | Leave blank if using IAM Role |
| `POLL_INTERVAL_SECONDS` | worker | How often to check DB (default 30s) |

---

## API Endpoints (Backend, port 5000)

| Method | Path | Description | AWS Service |
|---|---|---|---|
| `GET` | `/api/health` | Liveness + DB check | RDS |
| `GET` | `/api/items` | List all items | RDS (read) |
| `POST` | `/api/items` | Create item + notify | RDS (write) + SNS |
| `POST` | `/api/upload` | Upload file + notify | S3 + RDS + SNS |
| `GET` | `/api/uploads` | List all upload records | RDS (read) |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `502 Bad Gateway` from Nginx | Backend isn't running on Server 2. Check `systemctl status backend` |
| `Database connection failed` | Check RDS security group — allow inbound 5432 from Backend/Worker EC2 security groups |
| `S3 upload failed` | Check IAM Role (or access keys) has `s3:PutObject` permission on the bucket |
| `SNS notification skipped` | Check `SNS_TOPIC_ARN` is set. Confirm email subscription in SNS console |
| Worker not updating items | Check `systemctl status worker`. Look at `journalctl -u worker` for DB errors |
| Can't reach backend from Nginx | Verify Nginx `proxy_pass` uses the **private** IP of Server 2, port 5000 |
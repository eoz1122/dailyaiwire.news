# DailyAIWire.news - VPS Deployment Guide

## Current Production Baseline

Verified on 2026-04-28:

- Production app path: `/home/dailyai/dailyaiwire.news`
- Process manager: Supervisor
- Active Supervisor programs: `dailyaiwire`, `dailyaiwire_fetcher`, `tweet_scheduler`
- Active Google credential path: `/home/dailyai/.secrets/google-cloud.json`
- Default deploy model: push committed code to GitHub, pull on VPS, restart Supervisor services
- Avoid direct local-to-VPS sync of uncommitted files. That was the main source of drift during cleanup.

## 🚀 Quick Deploy to Ubuntu VPS

### 1. Initial Server Setup

```bash
# SSH into your VPS
ssh dailyai@72.62.95.46

# Update system
apt update && apt upgrade -y

# Install Python 3.11 and dependencies
apt install python3.11 python3.11-venv python3-pip nginx supervisor git -y

# Create app user
adduser dailyai
usermod -aG sudo dailyai
su - dailyai
```

### 2. Clone and Setup Application

```bash
# Clone your repository
cd /home/dailyai
git clone https://github.com/eoz1122/dailyaiwire.news.git
cd dailyaiwire.news

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
nano .env  # Add your GEMINI_API_KEY and domain
```

### 3. Initialize Database

```bash
# Run fetcher once to create database and fetch initial articles
python fetcher.py
```

### 3b. Setup Audio Generation (Google TTS)

1. Go to Google Cloud Console and enable **Cloud Text-to-Speech API**.
2. Create a **Service Account** and generate a **JSON Key**.
3. Store the key outside the repo:

```bash
mkdir -p /home/dailyai/.secrets
mv google-cloud.json /home/dailyai/.secrets/google-cloud.json
chmod 600 /home/dailyai/.secrets/google-cloud.json
```

4. Update `.env`:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/home/dailyai/.secrets/google-cloud.json
```

Do not keep the credential JSON in the repo root.

### 4. Configure Gunicorn

Create `/home/dailyai/dailyaiwire.news/gunicorn_config.py`:

```python
bind = "127.0.0.1:8000"
workers = 4
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2
errorlog = "/home/dailyai/dailyaiwire.news/logs/gunicorn-error.log"
accesslog = "/home/dailyai/dailyaiwire.news/logs/gunicorn-access.log"
loglevel = "info"
```

Create logs directory:

```bash
mkdir -p /home/dailyai/dailyaiwire.news/logs
```

### 5. Configure Supervisor (Process Manager)

Create `/etc/supervisor/conf.d/dailyaiwire.conf`:

```ini
[program:dailyaiwire]
directory=/home/dailyai/dailyaiwire.news
command=/home/dailyai/dailyaiwire.news/venv/bin/gunicorn -c gunicorn_config.py app:app
user=dailyai
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=/home/dailyai/dailyaiwire.news/logs/supervisor-error.log
stdout_logfile=/home/dailyai/dailyaiwire.news/logs/supervisor-access.log
```

Start supervisor:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start dailyaiwire
sudo supervisorctl status
```

### 5b. Configure Fetcher Supervisor Service

Production currently runs the fetcher as a long-lived Supervisor program, not from cron.

Create `/etc/supervisor/conf.d/dailyaiwire_fetcher.conf`:

```ini
[program:dailyaiwire_fetcher]
directory=/home/dailyai/dailyaiwire.news
command=/home/dailyai/dailyaiwire.news/venv/bin/python fetcher.py --loop
user=dailyai
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=/home/dailyai/dailyaiwire.news/logs/fetcher-error.log
stdout_logfile=/home/dailyai/dailyaiwire.news/logs/fetcher.log
```

Start services:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start dailyaiwire dailyaiwire_fetcher
sudo supervisorctl status dailyaiwire dailyaiwire_fetcher
```

### 5c. Configure Twitter Scheduler (Optional)

This is not part of the current production baseline. Only enable it if you intentionally decouple social posting from the fetcher loop.

Create `/etc/supervisor/conf.d/tweet_scheduler.conf`:

```ini
[program:tweet_scheduler]
directory=/home/dailyai/dailyaiwire.news
command=/home/dailyai/dailyaiwire.news/venv/bin/python tweet_scheduler.py
user=dailyai
autostart=true
autorestart=true
stderr_logfile=/home/dailyai/dailyaiwire.news/logs/twitter-error.log
stdout_logfile=/home/dailyai/dailyaiwire.news/logs/twitter-access.log
```

Start service:

```bash
sudo supervisorctl update
sudo supervisorctl start tweet_scheduler
```

### 6. Configure Nginx

Create `/etc/nginx/sites-available/dailyaiwire`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Static files
    location /static {
        alias /home/dailyai/dailyaiwire.news/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Proxy to Gunicorn
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    # Increase timeout for long requests
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/dailyaiwire /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 7. Setup SSL with Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Follow prompts and select option 2 (redirect HTTP to HTTPS).

### 8. Legacy Cron Fallback

Production currently uses `dailyaiwire_fetcher` under Supervisor. Do not enable cron and Supervisor for the same fetcher workload at the same time.

If you ever need a temporary fallback one-shot fetch job, use cron deliberately and remove it once Supervisor is restored:

```cron
0 * * * * cd /home/dailyai/dailyaiwire.news && /home/dailyai/dailyaiwire.news/venv/bin/python fetcher.py >> /home/dailyai/dailyaiwire.news/logs/fetcher.log 2>&1
```

### 9. Firewall Configuration

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 10. Recommended Production Deploy

VPS prerequisite for non-root deploys:

```sudoers
Cmnd_Alias DAILYAIWIRE_SUPERVISOR = /usr/bin/supervisorctl restart dailyaiwire, /usr/bin/supervisorctl status dailyaiwire, /usr/bin/supervisorctl restart dailyaiwire_fetcher, /usr/bin/supervisorctl status dailyaiwire_fetcher
dailyai ALL=(root) NOPASSWD: DAILYAIWIRE_SUPERVISOR
```

Validate it once after installation:

```bash
sudo visudo -cf /etc/sudoers.d/dailyaiwire-supervisor
```

If X posting is enabled through the decoupled scheduler, include the scheduler in the same limited alias:

```sudoers
Cmnd_Alias DAILYAIWIRE_SUPERVISOR = /usr/bin/supervisorctl restart dailyaiwire, /usr/bin/supervisorctl status dailyaiwire, /usr/bin/supervisorctl restart dailyaiwire_fetcher, /usr/bin/supervisorctl status dailyaiwire_fetcher, /usr/bin/supervisorctl restart tweet_scheduler, /usr/bin/supervisorctl status tweet_scheduler
dailyai ALL=(root) NOPASSWD: DAILYAIWIRE_SUPERVISOR
```

Do not grant `dailyai` general `supervisorctl` access or broad passwordless sudo. Keep the rule limited to the DailyAIWire programs above.

```bash
# Commit and push first
git push origin main

# SSH to the VPS
ssh dailyai@72.62.95.46

# Deploy the exact ref now on main
cd /home/dailyai/dailyaiwire.news
./deploy_to_vps.sh --ref origin/main
```

This defaults to a web-only deploy. If fetcher-related code changed and you intentionally want the fetcher restarted too:

```bash
./deploy_to_vps.sh --ref origin/main --with-fetcher
```

Scheduler-related changes are auto-detected for `tweet_scheduler.py`, `social_distributor.py`, `url_shortener.py`, and `requirements.txt`. To force a scheduler restart even without detected file changes:

```bash
./deploy_to_vps.sh --ref origin/main --with-scheduler
```

For an intentional rollback to a previous commit:

```bash
./deploy_to_vps.sh --ref <previous-sha> --allow-reset
```

Do not rsync or copy uncommitted local files directly into production.

### 10b. GitHub Actions Production Deploy

For a more standard audited deploy path, use the manual `Deploy Production` workflow in GitHub Actions.

Required GitHub environment or repository secrets:

- `PROD_HOST`
- `PROD_USER`
- `PROD_SSH_KEY`

Recommended usage:

1. Push the commit you want to deploy.
2. Open GitHub Actions.
3. Run `Deploy Production`.
4. Deploy the exact ref or SHA you want.
5. Leave `restart_fetcher` off for normal web-only deploys.
6. Turn `restart_fetcher` on only when fetcher code or runtime dependencies changed.
7. Turn `restart_scheduler` on only when you need to force a scheduler restart without scheduler-related file changes.

---

## 🔄 Deployment Updates

When you push code changes:

```bash
cd /home/dailyai/dailyaiwire.news
./deploy_to_vps.sh --ref origin/main
```

---

## 📊 Monitoring Commands

```bash
# Check app status
sudo -n supervisorctl status dailyaiwire
sudo -n supervisorctl status dailyaiwire_fetcher
sudo -n supervisorctl status tweet_scheduler

# View logs
tail -f /home/dailyai/dailyaiwire.news/logs/gunicorn-error.log
tail -f /home/dailyai/dailyaiwire.news/logs/fetcher.log
tail -f /home/dailyai/dailyaiwire.news/logs/supervisor-error.log

# Restart services
sudo -n supervisorctl restart dailyaiwire
sudo -n supervisorctl restart dailyaiwire_fetcher
sudo -n supervisorctl restart tweet_scheduler
sudo systemctl restart nginx

# Check Nginx
sudo nginx -t
sudo systemctl status nginx
```

---

## 🛡️ Security Checklist

- [ ] Change default SSH port (optional but recommended)
- [ ] Disable root SSH login
- [ ] Setup fail2ban for brute force protection
- [ ] Regular system updates: `apt update && apt upgrade`
- [ ] Monitor logs regularly
- [ ] Backup database daily
- [ ] Validate `/etc/sudoers.d/dailyaiwire-supervisor` with `sudo visudo -cf /etc/sudoers.d/dailyaiwire-supervisor`

---

## 📈 Performance Optimization

### Database Backup Script

Create `/home/dailyai/backup_db.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/home/dailyai/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
cp /home/dailyai/dailyaiwire.news/news.db $BACKUP_DIR/news_$DATE.db
# Keep only last 7 days
find $BACKUP_DIR -name "news_*.db" -mtime +7 -delete
```

Make executable and add to cron:

```bash
chmod +x /home/dailyai/backup_db.sh
crontab -e
# Add: 0 2 * * * /home/dailyai/backup_db.sh
```

---

## 🚨 Troubleshooting

**App won't start:**

```bash
sudo supervisorctl tail dailyaiwire stderr
```

**502 Bad Gateway:**

- Check if Gunicorn is running: `sudo supervisorctl status`
- Check Nginx config: `sudo nginx -t`

**Database locked:**

```bash
# Stop app, backup DB, restart
sudo supervisorctl stop dailyaiwire
cp news.db news.db.backup
sudo supervisorctl start dailyaiwire
```

---

## 📞 Support

For issues, check logs first:

- Gunicorn: `/home/dailyai/dailyaiwire.news/logs/gunicorn-error.log`
- Fetcher: `/home/dailyai/dailyaiwire.news/logs/fetcher.log`
- Supervisor: `/home/dailyai/dailyaiwire.news/logs/supervisor-error.log`
- Nginx: `/var/log/nginx/error.log`

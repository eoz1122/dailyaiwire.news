# DailyAIWire.news - VPS Deployment Guide

## 🚀 Quick Deploy to Ubuntu VPS

### 1. Initial Server Setup

```bash
# SSH into your VPS
ssh root@your-server-ip

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
git clone https://github.com/yourusername/dailyaiwire.news.git
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
2. Create time a **Service Account** and generate a **JSON Key**.
3. Upload the key file to the server (e.g., `google_credentials.json`).
4. Update `.env`:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/home/dailyai/dailyaiwire/google_credentials.json
```

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

### 5b. Configure Twitter Scheduler (Optional)

To run the social media scheduler independently (posts every 1 hour):

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
sudo supervisorctl start dailyaiwire-twitter
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

### 8. Setup Cron Job for Fetcher

```bash
crontab -e
```

Add this line to run fetcher every hour:

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

---

## 🔄 Deployment Updates

When you push code changes:

```bash
cd /home/dailyai/dailyaiwire.news
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo supervisorctl restart dailyaiwire
sudo supervisorctl restart tweet_scheduler
```

---

## 📊 Monitoring Commands

```bash
# Check app status
sudo supervisorctl status dailyaiwire

# View logs
tail -f /home/dailyai/dailyaiwire/logs/gunicorn-error.log
tail -f /home/dailyai/dailyaiwire/logs/fetcher.log

# Restart services
sudo supervisorctl restart dailyaiwire
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

---

## 📈 Performance Optimization

### Database Backup Script

Create `/home/dailyai/backup_db.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/home/dailyai/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
cp /home/dailyai/dailyaiwire/news.db $BACKUP_DIR/news_$DATE.db
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

- Gunicorn: `/home/dailyai/dailyaiwire/logs/gunicorn-error.log`
- Fetcher: `/home/dailyai/dailyaiwire/logs/fetcher.log`
- Nginx: `/var/log/nginx/error.log`

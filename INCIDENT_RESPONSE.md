# DailyAIWire.news — Incident Response Playbook

> **Version:** 1.0 | **Last Updated:** April 2026
> Keep this document up to date after every postmortem.

---

## Quick Reference

| Severity | Criteria | Response Target |
|----------|----------|----------------|
| SEV1 | Site completely down, all readers affected | Immediate — drop everything |
| SEV2 | Major feature broken (articles not loading, no new content for 4+ hrs) | Within 15 minutes |
| SEV3 | Degraded experience (slow load times, single section broken, social posting down) | Within 1 hour |
| SEV4 | Cosmetic or low-impact issue (layout glitch, one article missing) | Next available time |

**Key log locations:**
```
/home/dailyai/dailyaiwire.news/logs/gunicorn-error.log
/home/dailyai/dailyaiwire.news/logs/fetcher.log
/home/dailyai/dailyaiwire.news/logs/supervisor-error.log
/var/log/nginx/error.log
/var/log/nginx/access.log
```

**Server:** `ssh dailyai@72.62.95.46`

---

## Phase 1: Triage

### Step 1 — Confirm the incident

Before declaring an incident, verify the issue is real and not a local/browser problem.

```bash
# Check if the site responds
curl -I https://dailyaiwire.news

# Run QA monitor against homepage
python qa_monitor.py https://dailyaiwire.news

# Check all supervisor processes
sudo supervisorctl status

# Check Nginx
sudo systemctl status nginx
```

### Step 2 — Classify severity

Ask:
- Is the site returning 5xx errors or timing out? → **SEV1**
- Are articles loading but no new content has appeared in 4+ hours? → **SEV2**
- Is one feature broken (audio, social posting, a specific route)? → **SEV3**
- Is it cosmetic only? → **SEV4**

### Step 3 — Assign roles

Even as a solo operator, name these roles explicitly when looping others in:

| Role | Responsibility |
|------|---------------|
| **Incident Commander (IC)** | Owns the incident. Makes decisions, declares resolution. |
| **Responder** | Executes technical fixes. |
| **Comms** | Posts status updates, responds to readers. |

---

## Phase 2: Communicate

### Internal status update template

Post to your team chat / notes immediately when an incident starts — even before you know the cause.

```
🚨 INCIDENT OPEN — [Title]
Severity: SEV[X]
Time detected: [HH:MM UTC]
Impact: [What's broken / who's affected]
Current status: Investigating
Next update: In [15/30/60] minutes
```

### Reader-facing communication (SEV1 / SEV2 only)

Use social media or a status page if you have one. Keep it factual — no speculation.

**Template:**
```
We're aware of an issue affecting [feature/the site].
Our team is actively investigating. We'll share an update by [time].
We apologize for any inconvenience.
```

**Resolution notice:**
```
✅ Resolved: [Brief description of what happened and what was fixed].
Service restored at [HH:MM UTC]. Thank you for your patience.
```

---

## Phase 3: Diagnose & Mitigate

Work through the most likely failure modes for your stack, in order.

### Runbook A — Site down / 502 Bad Gateway

```bash
# 1. Check if Gunicorn is running
sudo supervisorctl status dailyaiwire

# 2. If stopped, restart it
sudo supervisorctl restart dailyaiwire

# 3. Watch logs for startup errors
tail -f /home/dailyai/dailyaiwire.news/logs/gunicorn-error.log

# 4. If Gunicorn is up but still 502, check Nginx
sudo nginx -t
sudo systemctl restart nginx

# 5. Verify the app is actually binding to the expected port
ss -tlnp | grep 8000
```

**Common causes:** Bad deploy (syntax error in code), Gunicorn crashed, Nginx misconfiguration.

---

### Runbook B — No new articles (fetcher failure)

```bash
# 1. Check fetcher supervisor process
sudo supervisorctl status dailyaiwire_fetcher

# 2. Check when fetcher last ran successfully
tail -50 /home/dailyai/dailyaiwire.news/logs/fetcher.log

# 3. Restart fetcher if it is stopped or wedged
sudo supervisorctl restart dailyaiwire_fetcher

# 4. Run fetcher manually to see errors
cd /home/dailyai/dailyaiwire.news
source venv/bin/activate
python fetcher.py

# 5. Check Gemini API quota (look for quota errors in output)
# If quota exhausted, wait for reset (midnight Pacific) or reduce fetch frequency

# 6. Check RSS source connectivity
curl -I https://www.theverge.com/rss/index.xml
curl -I https://techcrunch.com/feed/
```

**Common causes:** Fetcher supervisor process stopped, Gemini API quota exhausted, upstream RSS feeds unreachable, or a bad deploy introduced a runtime error.

---

### Runbook C — Database issues

```bash
# 1. Check if DB is accessible
sqlite3 /home/dailyai/dailyaiwire.news/news.db ".tables"

# 2. If "database is locked" error:
sudo supervisorctl stop dailyaiwire
cp news.db news.db.backup_$(date +%Y%m%d_%H%M%S)
# Check for orphaned connections
fuser news.db
sudo supervisorctl start dailyaiwire

# 3. If database is corrupted:
sqlite3 news.db "PRAGMA integrity_check;"
# If corruption found, restore from backup:
ls /home/dailyai/backups/
sudo supervisorctl stop dailyaiwire
cp /home/dailyai/backups/news_[LATEST].db news.db
sudo supervisorctl start dailyaiwire

# 4. Verify restore
python qa_monitor.py https://dailyaiwire.news
```

---

### Runbook D — Social posting down

```bash
# 1. Check which process is handling posting on this host
sudo supervisorctl status | grep -E "tweet_scheduler|dailyaiwire_fetcher"

# 2. Check scheduler and fetcher logs
tail -50 /home/dailyai/dailyaiwire.news/logs/twitter-error.log 2>/dev/null || true
tail -50 /home/dailyai/dailyaiwire.news/logs/fetcher.log

# 3. Restart the relevant process
sudo supervisorctl restart tweet_scheduler
sudo supervisorctl restart dailyaiwire_fetcher

# 4. Check social API credentials and recent rate-limit errors in .env / logs
# If API rate limited: wait for reset window (check Twitter Developer Portal)
```

**Note:** Social posting failure is SEV3 at most — it does not affect site availability.

---

### Runbook E — Audio generation down (Google TTS)

```bash
# 1. Check if credentials file exists and is accessible
ls -la /home/dailyai/.secrets/google-cloud.json

# 2. Check .env and confirm it points outside the repo
grep GOOGLE_APPLICATION_CREDENTIALS /home/dailyai/dailyaiwire.news/.env

# 3. Test TTS API connectivity
# Look for auth errors in gunicorn logs
tail -100 /home/dailyai/dailyaiwire.news/logs/gunicorn-error.log | grep -i "audio\|tts\|google"

# 4. If credentials expired: regenerate JSON key in Google Cloud Console
```

---

### Runbook F — SSL / HTTPS issues

```bash
# 1. Check cert expiry
sudo certbot certificates

# 2. Renew if expiring soon (auto-renewal should handle this but verify)
sudo certbot renew --dry-run
sudo certbot renew

# 3. Restart Nginx after renewal
sudo systemctl restart nginx
```

---

### Runbook G — Emergency rollback

If a bad deploy causes the site to break:

```bash
# 1. Find last working commit
git log --oneline -10

# 2. Roll back to previous commit
git revert HEAD --no-edit
# OR hard reset to specific commit (use with caution):
git reset --hard [COMMIT_HASH]

# 3. Restart app
sudo supervisorctl restart dailyaiwire

# 4. Verify
python qa_monitor.py https://dailyaiwire.news
```

---

## Phase 4: Resolution & Postmortem

### Declaring resolution

Before closing an incident, verify:
- [ ] Site is returning 200 for homepage and article pages
- [ ] `qa_monitor.py` passes
- [ ] New articles are appearing on schedule (or manually confirmed)
- [ ] No new errors in Gunicorn logs
- [ ] Supervisor shows all processes as `RUNNING`

Post resolution notice using the template in Phase 2.

### When to write a postmortem

Write a postmortem for **any SEV1 or SEV2 incident**, or any SEV3 that recurred more than once.

---

## Postmortem Template

Copy this and fill it in within 24–48 hours of resolution.

```markdown
## Postmortem: [Incident Title]

**Date:** [YYYY-MM-DD]
**Duration:** [X hours Y minutes]
**Severity:** SEV[X]
**Author:** [Name]
**Status:** Draft → Final

---

### Summary
[2–3 sentences describing what happened, the impact, and how it was resolved.]

### Impact
- **Readers affected:** [All / partial — describe]
- **Duration of outage:** [HH:MM – HH:MM UTC]
- **Features affected:** [e.g., article page loads, fetcher, social posting]

### Timeline

| Time (UTC) | Event |
|------------|-------|
| HH:MM | Issue first detected |
| HH:MM | Incident declared |
| HH:MM | Root cause identified |
| HH:MM | Mitigation applied |
| HH:MM | Incident resolved |

### Root Cause
[Detailed explanation of what actually caused the incident.]

### 5 Whys

1. Why did [symptom]? → [Because...]
2. Why did [cause 1]? → [Because...]
3. Why did [cause 2]? → [Because...]
4. Why did [cause 3]? → [Because...]
5. Why did [cause 4]? → [Root cause]

### What Went Well
- [Things that helped you detect / resolve faster]

### What Went Poorly
- [Things that slowed you down or made the impact worse]

### Action Items

| Action | Owner | Priority | Due Date |
|--------|-------|----------|----------|
| [Specific fix or improvement] | [Name] | P0/P1/P2 | [Date] |

### Lessons Learned
[Key takeaway(s) that will improve reliability or response for next time.]
```

---

## Recommended Improvements (Prioritized)

These are the highest-value investments to improve your incident posture:

| Priority | Action | Why |
|----------|--------|-----|
| **P0** | Set up uptime monitoring (UptimeRobot, BetterStack — free tiers available) | Currently you'd only know the site is down if a reader tells you |
| **P0** | Add email/SMS alerting when Gunicorn or Nginx fails | Supervisor can restart processes but won't alert you |
| **P1** | Verify daily DB backup cron is actually running | `backup_db.sh` exists but confirm it's in crontab |
| **P1** | Add a `/health` endpoint to your Flask app for monitoring pings | Easier to check than scraping the homepage |
| **P1** | Document your Gemini API quota limit and reset time | Quota exhaustion is your most likely SEV2 failure mode |
| **P2** | Set up Nginx access log alerting for spike in 5xx errors | Early warning before a full outage |
| **P2** | Keep a `CHANGELOG.md` — helps with timeline reconstruction in postmortems | |
| **P2** | Test your DB restore procedure before you need it | Backups are useless if you've never tested recovery |

---

## Monitoring Quick-Setup (UptimeRobot — Free)

1. Sign up at [uptimerobot.com](https://uptimerobot.com)
2. Add monitor: HTTP(s) → `https://dailyaiwire.news` → every 5 minutes
3. Add alert contact: your email
4. Optional: add a second monitor for `https://dailyaiwire.news/sitemap.xml` (confirms routes work)

This gives you instant email/SMS when the site goes down — filling your biggest monitoring gap.

---

*This playbook is a living document. Update it after every postmortem with new runbooks and lessons learned.*

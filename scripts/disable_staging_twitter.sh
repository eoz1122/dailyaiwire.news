#!/bin/bash
# Script to disable staging and Twitter scheduler

echo "======================================================================"
echo "🛑 DISABLING STAGING & TWITTER SCHEDULER"
echo "======================================================================"
echo ""

# Stop the services
echo "Stopping services..."
supervisorctl stop dailyaiwire-staging
supervisorctl stop tweet_scheduler

echo ""
echo "✅ Services stopped"
echo ""

# Show current status
echo "Current supervisor status:"
supervisorctl status

echo ""
echo "======================================================================"
echo "💡 TO PERMANENTLY DISABLE (prevent auto-start on reboot):"
echo "======================================================================"
echo ""
echo "Edit the supervisor config files:"
echo ""
echo "1. For staging:"
echo "   sudo nano /etc/supervisor/conf.d/dailyaiwire-staging.conf"
echo "   Change: autostart=true  →  autostart=false"
echo ""
echo "2. For Twitter scheduler:"
echo "   sudo nano /etc/supervisor/conf.d/tweet_scheduler.conf"
echo "   Change: autostart=true  →  autostart=false"
echo ""
echo "3. Reload supervisor:"
echo "   sudo supervisorctl reread"
echo "   sudo supervisorctl update"
echo ""
echo "======================================================================"

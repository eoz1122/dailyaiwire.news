#!/bin/bash
# VPS Fallback Image Diagnostic & Fix Script

echo "======================================================================"
echo "🔍 DAILYAIWIRE VPS IMAGE DIAGNOSTIC"
echo "======================================================================"
echo ""

# 1. Check if we're in the right directory
echo "📂 Current directory:"
pwd
echo ""

# 2. Check if fallback directory exists
echo "📁 Checking static/fallbacks/ directory:"
if [ -d "static/fallbacks" ]; then
    echo "✅ Directory exists"
    echo ""
    echo "📊 Files in static/fallbacks/:"
    ls -lh static/fallbacks/*.jpg 2>/dev/null || echo "❌ No .jpg files found!"
else
    echo "❌ Directory does NOT exist!"
    echo "   Creating directory..."
    mkdir -p static/fallbacks
fi
echo ""

# 3. Check git status
echo "🔄 Git status:"
git status --short
echo ""

# 4. Check if images are in git
echo "📦 Images tracked in git:"
git ls-files static/fallbacks/ | wc -l
echo ""

# 5. Run Python diagnostic
echo "🐍 Running database diagnostic:"
python scripts/check_vps_images.py
echo ""

# 6. Test image accessibility
echo "🌐 Testing image URL accessibility:"
curl -I https://dailyaiwire.news/static/fallbacks/business_0.jpg 2>&1 | head -n 1
echo ""

echo "======================================================================"
echo "💡 RECOMMENDED ACTIONS:"
echo "======================================================================"
echo ""
echo "If images are missing from static/fallbacks/:"
echo "  1. git pull origin main"
echo "  2. git checkout 14f6a85 -- static/fallbacks/"
echo "  3. supervisorctl restart dailyai"
echo ""
echo "If database has wrong URLs:"
echo "  1. python scripts/fix_fallback_urls.py"
echo "  2. python scripts/randomize_existing_images.py"
echo ""
echo "======================================================================"

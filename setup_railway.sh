#!/bin/bash

# Railway Deployment Helper Script
# This script helps you prepare for Railway deployment

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║                                                       ║"
echo "║         🚂 RAILWAY DEPLOYMENT HELPER 🚂               ║"
echo "║                                                       ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "❌ Error: Not a git repository"
    echo ""
    read -p "Initialize git repository now? [Y/n] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        git init
        echo "✅ Git repository initialized"
    else
        echo "Cancelled. Please initialize git first: git init"
        exit 1
    fi
fi

echo "📋 Pre-deployment Checklist:"
echo ""

# Check Procfile
if [ -f "Procfile" ]; then
    echo "✅ Procfile exists"
    echo "   Content: $(cat Procfile)"
else
    echo "⚠️  Procfile not found"
    echo "   Creating Procfile..."
    echo "worker: python stock_tracker.py" > Procfile
    echo "✅ Procfile created"
fi

# Check runtime.txt
if [ -f "runtime.txt" ]; then
    echo "✅ runtime.txt exists"
    echo "   Python version: $(cat runtime.txt)"
else
    echo "⚠️  runtime.txt not found"
    echo "   Creating runtime.txt..."
    echo "python-3.11.5" > runtime.txt
    echo "✅ runtime.txt created"
fi

# Check requirements.txt
if [ -f "requirements.txt" ]; then
    echo "✅ requirements.txt exists"
else
    echo "❌ requirements.txt not found"
    echo "   Please create requirements.txt with dependencies"
    exit 1
fi

# Check if stock_tracker.py exists
if [ -f "stock_tracker.py" ]; then
    echo "✅ stock_tracker.py exists"
else
    echo "❌ stock_tracker.py not found"
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════"
echo "🎯 Telegram Bot Setup"
echo "════════════════════════════════════════════════════════"
echo ""
echo "You'll need these for Railway environment variables:"
echo ""

read -p "Have you created a Telegram bot? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "📱 Create a Telegram bot first:"
    echo "   1. Open Telegram and search: @BotFather"
    echo "   2. Send: /newbot"
    echo "   3. Follow instructions"
    echo "   4. Copy your bot token"
    echo "   5. Send a message to your bot"
    echo "   6. Visit: https://api.telegram.org/bot<TOKEN>/getUpdates"
    echo "   7. Copy your chat_id"
    echo ""
    read -p "Press Enter when ready to continue..."
fi

echo ""
read -p "Enter your Telegram bot token (or skip): " bot_token
read -p "Enter your Telegram chat ID (or skip): " chat_id

echo ""
echo "════════════════════════════════════════════════════════"
echo "📦 Preparing for Deployment"
echo "════════════════════════════════════════════════════════"
echo ""

# Add to gitignore
if [ ! -f ".gitignore" ]; then
    echo "Creating .gitignore..."
    cat > .gitignore << EOF
# Python
__pycache__/
*.py[cod]
*.so
*.egg-info/
dist/
build/

# Environment
.env
.env.local
*.log

# Config files with secrets
tracker_config.json
alert_history.json

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db
EOF
    echo "✅ .gitignore created"
else
    echo "✅ .gitignore exists"
fi

# Commit changes
echo ""
read -p "Commit changes to git? [Y/n] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    git add .
    git commit -m "Prepare for Railway deployment" || echo "Nothing to commit"
    echo "✅ Changes committed"
fi

# Check for GitHub remote
has_remote=$(git remote -v | grep origin || echo "")
if [ -z "$has_remote" ]; then
    echo ""
    echo "⚠️  No GitHub remote configured"
    echo ""
    read -p "Do you have a GitHub repository? [y/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter your GitHub repository URL: " repo_url
        git remote add origin "$repo_url"
        echo "✅ Remote added"
        echo ""
        read -p "Push to GitHub now? [Y/n] " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
            git branch -M main
            git push -u origin main
            echo "✅ Pushed to GitHub"
        fi
    else
        echo ""
        echo "📌 Create a GitHub repository:"
        echo "   1. Go to: https://github.com/new"
        echo "   2. Create repository"
        echo "   3. Run: git remote add origin <your-repo-url>"
        echo "   4. Run: git push -u origin main"
    fi
fi

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║                                                       ║"
echo "║           ✅ READY FOR RAILWAY DEPLOYMENT! ✅         ║"
echo "║                                                       ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""
echo "🚂 Next Steps:"
echo ""
echo "1. Go to: https://railway.app"
echo "2. Login with GitHub"
echo "3. Click: New Project → Deploy from GitHub repo"
echo "4. Select your repository"
echo "5. Add Environment Variables:"
echo ""

if [ ! -z "$bot_token" ]; then
    echo "   TELEGRAM_BOT_TOKEN=$bot_token"
fi
if [ ! -z "$chat_id" ]; then
    echo "   TELEGRAM_CHAT_ID=$chat_id"
fi

echo "   WATCHLIST=AAPL,MSFT,GOOGL,AMZN,TSLA"
echo "   SCAN_INTERVAL_MINUTES=30"
echo "   MIN_CONFIDENCE=MODERATE"
echo "   PYTHONUNBUFFERED=1"
echo ""
echo "6. Railway will automatically deploy!"
echo ""
echo "📚 Full Guide: RAILWAY_DEPLOYMENT_GUIDE.md"
echo ""
echo "💡 Pro Tip: Save your environment variables somewhere safe"
echo "   You can use .env.railway.example as a template"
echo ""
echo "════════════════════════════════════════════════════════"
echo ""

# Save env vars to file for reference
if [ ! -z "$bot_token" ] && [ ! -z "$chat_id" ]; then
    echo ""
    read -p "Save environment variables to .env.railway (for reference)? [Y/n] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        cat > .env.railway << EOF
# Railway Environment Variables
# Copy these to Railway dashboard → Variables

TELEGRAM_BOT_TOKEN=$bot_token
TELEGRAM_CHAT_ID=$chat_id
WATCHLIST=AAPL,MSFT,GOOGL,AMZN,TSLA,NVDA,META
SCAN_INTERVAL_MINUTES=30
MIN_CONFIDENCE=MODERATE
MIN_CRITERIA_MET=4
ALERT_COOLDOWN_HOURS=4
PYTHONUNBUFFERED=1
EOF
        echo "✅ Saved to .env.railway"
        echo "⚠️  Don't commit this file to git!"
    fi
fi

echo ""
echo "Happy Deploying! 🚀"
echo ""

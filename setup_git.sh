#!/bin/bash
# Quick Git Setup Script for Streamlit Deployment

echo "🚀 Stock Analyzer - GitHub Setup Script"
echo "========================================"
echo ""

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    echo "❌ Error: app.py not found. Are you in the right directory?"
    echo "Run this script from: /Users/bhargavbvs/Desktop/stockanalysis"
    exit 1
fi

echo "✅ Found app.py - in correct directory"
echo ""

# Check if git is already initialized
if [ -d ".git" ]; then
    echo "⚠️  Git already initialized. Skipping git init."
else
    echo "📝 Initializing Git repository..."
    git init
    echo "✅ Git initialized"
fi

echo ""
echo "📦 Adding files to Git..."
git add .

echo ""
echo "💾 Committing files..."
git commit -m "Initial commit - Stock analyzer with Streamlit and options trading" || echo "Note: No changes to commit (already committed)"

echo ""
echo "========================================"
echo "🎯 Next Steps:"
echo "========================================"
echo ""
echo "1. Create GitHub repository:"
echo "   - Go to: https://github.com/new"
echo "   - Repository name: stockanalysis"
echo "   - Make it Public or Private (your choice)"
echo "   - DON'T initialize with README (we already have one)"
echo "   - Click 'Create repository'"
echo ""
echo "2. Connect to GitHub (run these commands):"
echo "   git remote add origin https://github.com/YOUR_USERNAME/stockanalysis.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "   Replace YOUR_USERNAME with your actual GitHub username!"
echo ""
echo "3. Deploy on Streamlit:"
echo "   - Go to: https://streamlit.io/cloud"
echo "   - Sign in with GitHub"
echo "   - Click 'New app'"
echo "   - Select your repo: stockanalysis"
echo "   - Main file: app.py"
echo "   - Add secret: TELEGRAM_BOT_TOKEN"
echo "   - Click 'Deploy'"
echo ""
echo "========================================"
echo "✅ Local Git setup complete!"
echo "========================================"
echo ""
echo "📖 Full guide: See DEPLOYMENT_CHECKLIST.md"
echo ""

# DailyAIWire.news

**Essential AI Intelligence, Curated Daily**

An automated AI news aggregation platform powered by Google Gemini. Aggregates, analyzes, and presents AI/tech news from premium sources with intelligent summaries, sentiment analysis, and deep insights.

## ✨ Features

- 🤖 **AI-Powered Analysis** - Google Gemini processes every article
- 📰 **Multi-Source Aggregation** - The Verge, TechCrunch, Wired, Google News
- 🎨 **Premium UI** - Dark/Light modes, responsive design
- 🔍 **SEO Optimized** - Full meta tags, JSON-LD, sitemap
- 📊 **Sentiment Analysis** - Optimistic/Pessimistic outlooks with interactive tooltips
- 🔬 **Automation Lab** - Blog section for automation case studies
- ⚡ **Smart Deduplication** - Only processes new articles to save API quota

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Google Gemini API key

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/dailyaiwire.git
cd dailyaiwire

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### Run Locally

```bash
# Fetch initial articles
python fetcher.py

# Start Flask server
python app.py

# Visit http://localhost:5000
```

## 📦 Project Structure

```
dailyaiwire/
├── app.py                 # Flask application entrypoint
├── extensions.py          # Global extensions (CSRF, Limiter)
├── db.py                  # Database connection utilities
├── fetcher/               # RSS aggregation & AI intelligence pipeline
├── routes/                # Flask Blueprints (public, api, admin, auth, seo, lab)
├── services/              # External integrations (social, email, analytics)
├── scripts/               # Utility scripts (migrations, deduplication)
├── templates/             # Jinja2 HTML templates
├── static/                # CSS, JS, Images, Fonts
├── tests/                 # Pytest test suite
├── news.db                # SQLite database
└── requirements.txt       # Dependencies
```

## 🌐 Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete VPS deployment instructions.

**Quick Deploy:**

1. Setup Ubuntu VPS
2. Install Nginx + Supervisor
3. Configure SSL with Let's Encrypt
4. Setup cron job for hourly fetching

## 🔧 Configuration

### Environment Variables

```env
GEMINI_API_KEY=your_api_key_here
DOMAIN=yourdomain.com
FLASK_ENV=production
```

### Fetcher Schedule

Edit crontab to run fetcher:

```bash
0 * * * * cd /path/to/dailyaiwire && /path/to/venv/bin/python fetcher.py
```

## 📊 Database Schema

### Articles Table

- `slug` - URL-safe identifier
- `title` - Article headline
- `gist` - 1-2 sentence summary
- `why_it_matters` - Impact analysis
- `bull_case` / `bear_case` - Sentiment outlooks
- `key_details` - JSON array of bullet points
- `eli5` - Simplified explanation
- `deep_analysis` - 400+ word analysis
- `source` / `source_url` - Attribution
- `category` - LLMs, Robotics, Business, Tools
- `published_at` - ISO timestamp

### Blog Posts Table

- `slug`, `title`, `subtitle`, `content`, `image`, `published_at`

## 🎨 UI Features

- **Dark/Light Mode Toggle** - Persistent theme preference
- **Fresh Article Indicators** - "NEW Signal" badges for recent posts
- **Interactive Tooltips** - Hover over sentiment badges for full analysis
- **Source Attribution** - Branded badges for each publication
- **Responsive Design** - Mobile-first, works on all devices

## 🔐 Security

- Environment variables for sensitive data
- HTTPS enforced in production
- SQL injection protection (parameterized queries)
- XSS protection (Jinja2 auto-escaping)
- CSRF protection ready (add Flask-WTF if needed)

## 📈 SEO Features

- Dynamic meta tags (title, description, keywords)
- Open Graph tags for social sharing
- Twitter Cards
- JSON-LD structured data (NewsArticle schema)
- XML sitemap at `/sitemap.xml`
- robots.txt with AI crawler permissions
- Canonical URLs

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📝 License

MIT License - feel free to use for your own projects!

## 🙏 Acknowledgments

- **Google Gemini** - AI analysis engine
- **Tailwind CSS** - UI framework
- **Trafilatura** - Content extraction
- **Feedparser** - RSS parsing

## 📧 Contact

- Website: [dailyaiwire.news](https://dailyaiwire.news)
- Issues: [GitHub Issues](https://github.com/yourusername/dailyaiwire/issues)

---

**Built with ❤️ and AI**

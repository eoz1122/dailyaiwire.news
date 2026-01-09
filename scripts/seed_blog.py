import sqlite3
from slugify import slugify

DB_PATH = "news.db"

def seed_blog():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            title TEXT,
            subtitle TEXT,
            content TEXT,
            image TEXT,
            published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    title = "The Tiredless Team: How We Automated Our Entire Invoice Lifecycle"
    slug = slugify(title)
    subtitle = "Go behind the scenes of our n8n and Gemini-powered automation that handles everything from Google Drive monitoring to intelligent ledger matching."
    
    content = """
    <p>Think of this automation as a tireless member of the finance team who works 24/7. It lives inside a tool called <strong>n8n</strong> and handles the entire life cycle of an invoice without anyone lifting a finger:</p>
    
    <div class="my-8 rounded-2xl overflow-hidden border border-zinc-800 shadow-2xl">
        <img src="/static/n8n-workflow.png" alt="n8n AI Invoice Automation Workflow" class="w-full">
        <p class="text-center text-xs text-zinc-500 py-4 bg-zinc-900/50 italic">The actual n8n logic map showing the Gemini AI Agent handling the decision matrix.</p>
    </div>

    <h2>What Exactly Is This "Magic"? ✨</h2>
    <ul>
        <li><strong>The Watchman:</strong> Every few hours, it peeks into our Google Drive folders to see if any new invoices have landed.</li>
        <li><strong>The AI Brain:</strong> When it finds a PDF, it hands it over to <strong>Google Gemini AI</strong>. The AI "reads" the document just like a human would, pulling out the invoice numbers, totals, and specific campaign details.</li>
        <li><strong>The Matchmaker:</strong> It looks at the campaign names and uses AI to intelligently match them to our list of known advertisers—even if the names aren't a perfect 1:1 match.</li>
        <li><strong>The Librarian:</strong> Everything is then neatly filed away into a master Google Sheet, complete with a clean, human-readable timestamp so we know exactly when the data arrived.</li>
    </ul>

    <h2>Why We Love It (And You Will Too) 🚀</h2>
    <ul>
        <li><strong>Goodbye, Data Entry:</strong> We’ve officially retired the "copy-paste" routine. Invoices move from a folder to our spreadsheet in under an hour.</li>
        <li><strong>Early Warning System:</strong> If it's getting late in the month and a specific report is missing, the system sends a friendly nudge to the team: "Hi! We noticed this is missing; could you upload it when you have a chance?"</li>
        <li><strong>One Source of Truth:</strong> Because everything lands in one Google Sheet automatically, the whole team stays on the same page without having to hunt through email attachments.</li>
        <li><strong>AI-Driven Accuracy:</strong> By using AI for advertiser matching, we handle global data (US, UK, and beyond) with a level of consistency that manual work just can't beat.</li>
    </ul>

    <h2>The "Oops" Moments (And How We Fixed Them) 🛠️</h2>
    <p>It wasn't all smooth sailing! We ran into a few funny (and slightly stressful) hurdles along the way:</p>
    <ul>
        <li><strong>The Email Avalanche:</strong> At first, the system was so excited about the invoices that it sent an individual email for every single row added to the sheet. We quickly fixed that with a "Summarize" node, so now it sends just one professional, pretty update at the end of the batch.</li>
        <li><strong>The Identity Crisis:</strong> Sometimes the AI would get confused by multiple files at once. We wrote some custom JavaScript to help it stay organized and process everything as a single, clean batch.</li>
        <li><strong>The Date Drama:</strong> Getting dates to look "normal" (like 2025-12-18 15:30) instead of looking like computer code was a fun little puzzle, but our custom formatting script saved the day.</li>
    </ul>

    <h2>Where to Next? 🌎</h2>
    <p>The best part? This isn't just for invoices. Now that we’ve mastered the "Drive-to-AI-to-Sheet" pipeline, we can see this logic helping with:</p>
    <ul>
        <li><strong>HR:</strong> Processing new hire paperwork and updating rosters.</li>
        <li><strong>Legal:</strong> Keeping track of signed contracts in a master log.</li>
        <li><strong>Logistics:</strong> Managing shipping manifests and tracking deliveries.</li>
    </ul>
    <p>We’re so excited to keep pushing the boundaries of what AI can do for us. It’s not about replacing people; it’s about giving people their time back to do the creative, strategic work they enjoy!</p>
    """
    
    image = "/static/n8n-workflow.png" # Real n8n workflow screenshot
    
    cursor.execute('''
        INSERT OR REPLACE INTO blog_posts (slug, title, subtitle, content, image)
        VALUES (?, ?, ?, ?, ?)
    ''', (slug, title, subtitle, content, image))
    
    conn.commit()
    conn.close()
    print(f"Successfully seeded blog post: {title}")

if __name__ == "__main__":
    seed_blog()

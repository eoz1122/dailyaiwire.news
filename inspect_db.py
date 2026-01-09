import sqlite3

try:
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    
    # Check articles columns
    cursor.execute("PRAGMA table_info(articles)")
    columns = [info[1] for info in cursor.fetchall()]
    print("Articles Table Columns:", columns)
    
    # Identify URL column (heuristic)
    url_col = 'url'
    if 'source_url' in columns:
        url_col = 'source_url'
    elif 'link' in columns:
        url_col = 'link'
    elif 'original_url' in columns:
        url_col = 'original_url'
        
    print(f"Using '{url_col}' as URL column for articles.")
    
    # 1. Get SYSTEM KILLED (Explicitly Killed by Fetcher)
    cursor.execute("SELECT url, status, attempted_at FROM processing_attempts WHERE status IN ('REDIRECT_TO_LEAD_GEN', 'SKIPPED_LOW_CONTENT')")
    explicit_killed = cursor.fetchall() # list of (url, status, date)
    
    # 2. Get MANUALLY KILLED (Soft Deleted in Admin)
    # Check if is_published column exists
    if 'is_published' in columns:
        cursor.execute(f"SELECT {url_col}, 'MANUALLY_KILLED', published_at FROM articles WHERE is_published = 0")
        manual_killed = cursor.fetchall()
    else:
        manual_killed = []
        print("Warning: is_published column not found. Skipping manual kill check.")

    
    # Combine
    all_killed = explicit_killed + manual_killed
    
    print(f"\nSystem Killed: {len(explicit_killed)}")
    print(f"Manually Killed: {len(manual_killed)}")
    print(f"Total Killed: {len(all_killed)}")
    
    print("\n--- KILLED ARTICLES LIST ---\n")
    for row in all_killed:
        print(f"[{row[1]}] {row[0]}")
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")

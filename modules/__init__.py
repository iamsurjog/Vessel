from pathlib import Path
import sqlite3
import sqlite_vec


def updateEmbeds() -> bool:
    print("UPDATED")
    return True

def answerTo(id: str, message: str) -> str:
    return message + id

def initVessel(path: Path) -> bool:
    # 1. Ensure directory structures exist
    sys_dir = path / "AI" / ".sys"
    content_dir = path / "AI" / "content"
    
    sys_dir.mkdir(parents=True, exist_ok=True)
    content_dir.mkdir(parents=True, exist_ok=True)
    
    # Define our single, unified SQLite file destination
    db_file = sys_dir / "vessel_rag.db"
    
    # 2. Establish connection and initialize database schema
    try:
        conn = sqlite3.connect(db_file)
        
        # Enable runtime extensions and inject the vec0 runtime library
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        
        cursor = conn.cursor()
        
        # Enforce relational consistency constraints across tables
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        # Base table for standard document chunks
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                text_chunk TEXT NOT NULL
            );
        """)
        
        # Inverted index lookups for rapid tag tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
        """)
        
        # Many-to-Many junction mapping table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_tags (
                doc_id INTEGER,
                tag_id INTEGER,
                PRIMARY KEY (doc_id, tag_id),
                FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );
        """)
        
        # Build index directly on the junction pivot point to eliminate heavy table scanning
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag_search ON document_tags(tag_id, doc_id);")
        
        # Vector storage table (Defaulting to 768 dimensions for models like nomic-embed-text)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS v_document_embeddings USING vec0(
                embedding float[768]
            );
        """)
        
        conn.commit()
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database Initialization failed: {e}")
        return False

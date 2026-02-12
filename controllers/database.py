import sqlite3

def connect(db_path="data/shanano.db"):
    return sqlite3.connect(db_path)

def init_db(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY,
            name TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fingerprints (
            hash TEXT,
            song_id INTEGER,
            anchor_time INTEGER,
            anchor_freq INTEGER,
            target_time INTEGER,
            target_freq INTEGER
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_hash ON fingerprints(hash)")
    conn.commit()


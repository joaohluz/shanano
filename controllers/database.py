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
            offset INTEGER
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_hash ON fingerprints(hash)")
    conn.commit()

def add_song(conn, name, fingerprints):
    cur = conn.cursor()
    cur.execute("INSERT INTO songs (name) VALUES (?)", (name,))
    song_id = cur.lastrowid

    cur.executemany(
    "INSERT INTO fingerprints (hash, song_id, offset) VALUES (?, ?, ?)",
    [(str(h), int(song_id), int(offset)) for h, offset in fingerprints]
    )

    conn.commit()

# CRUD Service for songs in the database. This will be used by the CLI
from pathlib import Path
from sqlite3 import Connection 

from audio_processing.audio import load_audio
from audio_processing.spectrogram import spectrogram, find_peaks
from controllers.fingerprint import generate_fingerprints

def add_song(conn : Connection, file_path: str):
    file = Path(file_path)
    if not file.exists():
        return 1, f"Error: File '{file}' does not exist."
    
    print(f"Processing {file.name}...")
    y, sr = load_audio(file.as_posix())
    S_db = spectrogram(y, sr)
    peaks = find_peaks(S_db)
    fps = generate_fingerprints(peaks)
    persist_song_data(conn, file.stem, fps)
    msg = f"Added {file.stem}, {len(fps)} fingerprints"
    return 0, msg

def persist_song_data(conn : Connection, name, fingerprints):
    cur = conn.cursor()
    cur.execute("INSERT INTO songs (name) VALUES (?)", (name,))
    song_id = cur.lastrowid

    cur.executemany(
    "INSERT INTO fingerprints (hash, song_id, offset) VALUES (?, ?, ?)",
    [(str(h), int(song_id), int(offset)) for h, offset in fingerprints]
    )

    conn.commit()

def list_songs(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM songs")
    return [row[0] for row in cur.fetchall()]

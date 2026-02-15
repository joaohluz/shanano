# CRUD Service for songs in the database. This will be used by the CLI
from pathlib import Path
from sqlite3 import Connection 

from audio_processing.audio import load_audio
from audio_processing.spectrogram import spectrogram, find_peaks
from config import DEFAULT_AMP_MIN
from controllers.fingerprint import generate_fingerprints

def add_song(conn : Connection, file_path: str):
    file = Path(file_path)
    if not file.exists():
        return 1, f"Error: File '{file}' does not exist."
    
    print(f"Processing {file.name}...")
    y, sr = load_audio(file.as_posix())
    S_db = spectrogram(y)
    peaks = find_peaks(S_db, amp_min=DEFAULT_AMP_MIN)
    fps = generate_fingerprints(peaks)
    persist_song_data(conn, file.stem, fps)
    msg = f"Added {file.stem}, {len(fps)} fingerprints"
    return 0, msg

def persist_song_data(conn : Connection, name, fingerprints):
    cur = conn.cursor()
    cur.execute("INSERT INTO songs (name) VALUES (?)", (name,))
    song_id = cur.lastrowid

    cur.executemany(
    "INSERT INTO fingerprints (hash, song_id, anchor_time, anchor_freq, target_time, target_freq) VALUES (?, ?, ?, ?, ?, ?)",
    [(str(h), int(song_id), int(anchor_time), int(anchor_freq), int(target_time), int(target_freq)) for h, anchor_time, anchor_freq, target_time, target_freq in fingerprints]
    )

    conn.commit()

def list_songs(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM songs")
    return [row[0] for row in cur.fetchall()]

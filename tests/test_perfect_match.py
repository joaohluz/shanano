from collections import defaultdict
from pathlib import Path
import matplotlib.pyplot as plt
import time

from audio_processing.audio import record_audio, load_audio
from audio_processing.spectrogram import spectrogram, find_peaks
from controllers.database import connect, init_db, add_song
from controllers.fingerprint import generate_fingerprints
from controllers.match import recognize

# -------------------------------
# Setup DB (in memory)
# -------------------------------
conn = connect(":memory:")
init_db(conn)

# -------------------------------
# Load cleaned WAVs into DB
# -------------------------------
song_fps = {}
song_ids = []
clean_folder = Path("data", "assets", "clean_wavs")
print("Adding songs to DB from folder:", clean_folder)
#Check if folder exists
if not clean_folder.exists():
    print(f"Error: Folder {clean_folder} does not exist.")
    exit(1)
for wav_path in clean_folder.glob("*.wav"):
    print(f"Processing {wav_path.name}...")
    y, sr = load_audio(wav_path.as_posix())
    S_db = spectrogram(y, sr)
    peaks = find_peaks(S_db)
    fps = generate_fingerprints(peaks)
    add_song(conn, wav_path.stem, fps)
    song_fps[wav_path.stem] = fps
    song_ids.append(wav_path.stem)
    print(f"Added {wav_path.stem}, {len(fps)} fingerprints")


# -------------------------------
# Use each song as 'mic' input and analyze perfect match
# -------------------------------
for test_song_id, test_fps in song_fps.items():
    print(f"\n=== Using '{test_song_id}' as query (mic input) ===")
    offset_histograms = {}
    # Compare this song's fingerprints against all songs in DB
    for song_id, fps_song in song_fps.items():
        matches = []
        cur = conn.cursor()
        for h, offset in test_fps:
            cur.execute("SELECT offset FROM fingerprints WHERE hash=? AND song_id=(SELECT id FROM songs WHERE name=?)", (h, song_id))
            for (db_offset,) in cur.fetchall():
                matches.append(db_offset - offset)
        offset_histograms[song_id] = matches

    # Plot histogram for this query
    plt.figure(figsize=(12, 6))
    for song_id, offsets in offset_histograms.items():
        if offsets:
            plt.hist(offsets, bins=100, alpha=0.5, label=song_id)

    plt.title(f"Relative Time Offset Histogram: Query '{test_song_id}' vs DB")
    plt.xlabel("Time offset (frames)")
    plt.ylabel("Count of matching fingerprints")
    plt.legend()
    plt.show()

    # Recognition summary for this query
    results = recognize(conn, test_fps)
    if results:
        top_song_id, top_score = results[0]
        print("Recognition results:")
        print(f"Top match: {top_song_id} (score: {top_score})")
    else:
        print("No match found.")

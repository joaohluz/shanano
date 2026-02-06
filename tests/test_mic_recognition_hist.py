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
# Record from microphone
# -------------------------------
for i in range(3, 0, -1):
    print(f"\n--- Recording starts in {i} seconds ---")
    time.sleep(1)
y_mic, sr_mic = record_audio(duration=7)
print("Recording done.")

S_db_mic = spectrogram(y_mic, sr_mic)
peaks_mic = find_peaks(S_db_mic)
fps_mic = generate_fingerprints(peaks_mic)
print(f"Mic clip: {len(peaks_mic)} peaks, {len(fps_mic)} fingerprints")

# -------------------------------
# Custom matching for histogram
# -------------------------------
offset_histograms = {}

for song_id, fps_song in song_fps.items():
    matches = []
    cur = conn.cursor()
    for h, offset in fps_mic:
        cur.execute("SELECT offset FROM fingerprints WHERE hash=? AND song_id=(SELECT id FROM songs WHERE name=?)", (h, song_id))
        for (db_offset,) in cur.fetchall():
            matches.append(db_offset - offset)
    offset_histograms[song_id] = matches

# -------------------------------
# Plot histograms
# -------------------------------
plt.figure(figsize=(12, 6))
for song_id, offsets in offset_histograms.items():
    if offsets:
        plt.hist(offsets, bins=100, alpha=0.5, label=song_id)

plt.title("Relative Time Offset Histograms (Mic vs Songs)")
plt.xlabel("Time offset (frames)")
plt.ylabel("Count of matching fingerprints")
plt.legend()
plt.show()

# -------------------------------
# Recognition summary
# -------------------------------
results = recognize(conn, fps_mic)
if results:
    top_song_id, top_score = results[0]
    print("\nRecognition results:")
    print(f"Top match: {top_song_id} (score: {top_score})")
else:
    print("No match found.")

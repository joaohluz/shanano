from pathlib import Path
import time

from audio_processing.audio import load_audio, record_audio
from audio_processing.spectrogram import spectrogram, find_peaks
from controllers.database import connect, init_db
from controllers.fingerprint import generate_fingerprints
from controllers.match_service import match_fingerprints
from controllers.song_manager import persist_song_data
# -------------------------------
# Setup DB (in memory for testing)
# -------------------------------
conn = connect(":memory:")
init_db(conn)

# -------------------------------
# Load cleaned WAVs into DB
# -------------------------------
clean_folder = Path("data", "assets", "clean_wavs")
print("Adding songs to DB from folder:", clean_folder)
#Check if folder exists
if not clean_folder.exists():
    print(f"Error: Folder {clean_folder} does not exist.")
    exit(1)
song_ids = []

print("Adding songs to DB...")
for wav_path in clean_folder.glob("*.wav"):
    y, sr = load_audio(wav_path.as_posix())
    S_db = spectrogram(y)
    peaks = find_peaks(S_db)
    fps = generate_fingerprints(peaks)
    persist_song_data(conn, wav_path.stem, fps)
    song_ids.append(wav_path.stem)
    print(f"Added {wav_path.stem}, {len(fps)} fingerprints")

# -------------------------------
# Record from microphone
# -------------------------------
print("\n--- Recording 7 seconds from microphone ---")
time.sleep(1)
y_mic, sr_mic = record_audio(duration=7)
print("Recording done.")

# -------------------------------
# Generate fingerprints from mic
# -------------------------------
S_db_mic = spectrogram(y_mic)
peaks_mic = find_peaks(S_db_mic)
fps_mic = generate_fingerprints(peaks_mic)
print(f"Mic clip: {len(peaks_mic)} peaks, {len(fps_mic)} fingerprints")

# -------------------------------
# Recognize song from DB
# -------------------------------
results = match_fingerprints(conn, fps_mic)

if results:
    top_song_id, top_score = results[0]
    print("\nRecognition results:")
    print(f"Top match: {top_song_id} (score: {top_score})")
else:
    print("No match found.")

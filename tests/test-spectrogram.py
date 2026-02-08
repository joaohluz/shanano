import matplotlib.pyplot as plt
from pathlib import Path

from audio_processing.audio import load_audio
from audio_processing.spectrogram import spectrogram, find_peaks
from controllers.database import connect, init_db
from controllers.fingerprint import generate_fingerprints
from controllers.match_service import match
from controllers.song_manager import persist_song_data


# clean waves in data/clean_wavs
clean_folder = Path("data", "assets", "clean_wavs")
print("Processing WAV files in:", clean_folder)
conn = connect(":memory:")
init_db(conn)
fps = None
for wav_path in clean_folder.glob("*.wav"):
    y, sr = load_audio(wav_path.as_posix())
    S_db = spectrogram(y)
    peaks = find_peaks(S_db)
    

    print(wav_path.name, "peaks:", len(peaks))

    plt.imshow(S_db, aspect="auto", origin="lower")
    times, freqs = zip(*peaks) if peaks else ([], [])
    plt.scatter(times, freqs, s=1, c="red")
    plt.title(wav_path.name)
    plt.xlabel("Time")
    plt.ylabel("Frequency Bin")
    plt.show() 
    
    fps = generate_fingerprints(peaks)
    print("Number of fingerprints:", len(fps))
    print("Example:", fps[:5])
    persist_song_data(conn, "test_song", fps)

results = match(conn, fps)
print("Recognition results:", results)

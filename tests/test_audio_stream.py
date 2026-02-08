from pathlib import Path
import threading
import time
import numpy as np
import matplotlib.pyplot as plt
from audio_processing import spectrogram
from audio_processing.audio import load_audio
from audio_processing.audio_stream import AudioStream
from audio_processing.incremental_fingerprinter import IncrementalFingerprinter
from controllers import match_service
from controllers.database import connect, init_db
from controllers.fingerprint import generate_fingerprints
from controllers.song_manager import persist_song_data

def fingerprint_worker():
    while not match_service.match_found.is_set():
        buf = stream.get_buffer()
        new_fps = fingerprinter.process(buf)
        for fp in new_fps:
            match_service.submit_fingerprint(fp)
        time.sleep(0.5)

if __name__ == "__main__":

    # clean_folder = Path("data", "assets", "clean_wavs")
    # song_ids = []
    conn = connect()
    init_db(conn)
    # print("Adding songs to DB...")
    # for wav_path in clean_folder.glob("*.wav"):
    #     y, sr = load_audio(wav_path.as_posix())
    #     S_db = spectrogram.spectrogram(y)
    #     peaks = spectrogram.find_peaks(S_db)
    #     fps = generate_fingerprints(peaks)
    #     persist_song_data(conn, wav_path.stem, fps)
    #     song_ids.append(wav_path.stem)
    #     print(f"Added {wav_path.stem}, {len(fps)} fingerprints")

    stream = AudioStream()
    stream.start()

    # IncrementalFingerprinter: processes buffer and yields fingerprints
    fingerprinter = IncrementalFingerprinter(sr=stream.sr, window_sec=3.0)

    def fingerprint_worker():
        while not match_service.match_found.is_set():
            time.sleep(5)
            print("Start at time:", time.strftime("%H:%M:%S"))
            buf = stream.get_buffer()
            new_fps = fingerprinter.process(buf)
            match_service.submit_fingerprints(new_fps)
            print("Submitted fingerprints at time:", time.strftime("%H:%M:%S"))

    # Start threads
    match_service = match_service.MatchService()
    threading.Thread(target=fingerprint_worker).start()
    threading.Thread(target=match_service.run).start()

    # Main thread waits for match
    # fig, ax = plt.subplots()
    # while not match_service.match_found.is_set():
    #     time.sleep(0.1)
    #     try:
    #         for i in range(10000):
    #             buf = stream.get_buffer()
    #             ax.cla()
    #             ax.plot(buf)
    #             ax.set_title("Live Audio Waveform")
    #             ax.set_xlabel("Sample")
    #             ax.set_ylabel("Amplitude")
    #             plt.pause(0.1)
    #     except KeyboardInterrupt:
    #         pass
    #     finally:
    #         stream.stop()
    #         plt.ioff()
    #         plt.show()
    print("Match found:", match_service.match_result)
    stream.stop()
    # Once match is found, we can show the histogram of offsets for the matched song
    
    matches = []
    offset_histograms = {}
    cur = conn.cursor()
    for h, offset in fps_mic:
        cur.execute("SELECT offset FROM fingerprints WHERE hash=? AND song_id=(SELECT id FROM songs WHERE name=?)", (h, match_service.match_result))
        for (db_offset,) in cur.fetchall():
            matches.append(db_offset - offset)
    offset_histograms[match_service.match_result] = matches

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
    




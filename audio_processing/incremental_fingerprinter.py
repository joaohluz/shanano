import numpy as np
from audio_processing.spectrogram import spectrogram, find_peaks
from controllers.fingerprint import generate_fingerprints

class IncrementalFingerprinter:
    def __init__(self, sr, window_sec=1.0):
        self.sr = sr
        self.window_size = int(window_sec * sr)

    def process(self, buffer):
        start = max(0, len(buffer) - self.window_size)
        window = buffer[start:].copy()
        print(f"Processing buffer of size {len(buffer)}, window size {len(window)} starting at {start}")
        print(f"Shape of window: {window.shape}")
        S_db = spectrogram(window)
        peaks = find_peaks(S_db)
        print(f"Number of peaks detected: {len(peaks)}")
        fps = generate_fingerprints(peaks)
        print(f"Number of fingerprints generated: {len(fps)}")
        new_fps = [(h, t + start) for h, t in fps]
        print("Sending new fingerprints:", len(new_fps))
        return new_fps.copy()

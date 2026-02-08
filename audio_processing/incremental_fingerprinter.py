import numpy as np
from audio_processing.spectrogram import spectrogram, find_peaks
from controllers.fingerprint import generate_fingerprints

class IncrementalFingerprinter:
    def __init__(self, sr, window_sec=1.0):
        self.sr = sr
        self.window_size = int(window_sec * sr)

    def process(self, buffer):
        new_fps = []
        start = max(0, len(buffer) - self.window_size)
        window = buffer[start:]
        print(f"Processing buffer of size {len(buffer)}, window size {len(window)} starting at {start}")
        S_db = spectrogram(window)
        peaks = find_peaks(S_db)
        fps = generate_fingerprints(peaks)
        new_fps.extend((h, t + start) for h, t in fps)
        print("Sending new fingerprints:", len(new_fps))
        return new_fps.copy()

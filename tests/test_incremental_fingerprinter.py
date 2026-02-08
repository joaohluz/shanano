import time
from audio_processing.audio_stream import AudioStream
from audio_processing.incremental_fingerprinter import IncrementalFingerprinter

import threading
import matplotlib.pyplot as plt

stream = AudioStream()
fingerprinter = IncrementalFingerprinter(sr=stream.sr, window_sec=1, hop_sec=0.5)
print("Starting audio stream and incremental fingerprinting...")
stream.start()
plt.ion()
fig, ax = plt.subplots()

running = True

def process_fingerprints():
    i = 0
    while running:
        time.sleep(1.5)
        buf = stream.get_buffer()
        new_fps = fingerprinter.process(buf)
        i += 1

t = threading.Thread(target=process_fingerprints)
t.start()

try:
    while True:
        buf = stream.get_buffer()
        ax.cla()
        ax.plot(buf)
        ax.set_title("Live Audio Waveform")
        ax.set_xlabel("Sample")
        ax.set_ylabel("Amplitude")
        plt.pause(0.1)
except KeyboardInterrupt:
    print("Interrupted by user.")
finally:
    running = False
    t.join()
    stream.stop()
    plt.ioff()
    plt.show()
    print("Audio stream stopped.")

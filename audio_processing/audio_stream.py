import sounddevice as sd
import numpy as np
import threading
import queue

from config import DEFAULT_SR, BUFFER_SECONDS, CHUNK_SIZE

class AudioStream:
    def __init__(self, sr=DEFAULT_SR, buffer_seconds=BUFFER_SECONDS):
        self.sr = sr
        self.buffer_samples = int(buffer_seconds * sr)
        self.buffer = np.zeros(self.buffer_samples, dtype=np.float32)
        self.q = queue.Queue()
        self.running = False
        self.match_found = threading.Event()
        self.match_result = None

    def _audio_callback(self, indata, frames, time_info, status):
        # print(indata.shape)
        self.q.put(indata[:, 0].copy())

    def start(self):
        self.running = True
        self.stream = sd.InputStream(
            samplerate=self.sr,
            channels=1,
            blocksize=CHUNK_SIZE,
            callback=self._audio_callback
        )
        self.stream.start()
        self.thread = threading.Thread(target=self._update_buffer)
        self.thread.start()

    def _update_buffer(self):
        while self.running:
            chunk = self.q.get()
            chunk_len = len(chunk)
            self.buffer = np.roll(self.buffer, -chunk_len)
            self.buffer[-chunk_len:] = chunk

    def stop(self):
        self.running = False
        self.stream.stop()
        self.thread.join()

    def get_buffer(self):
        return self.buffer.copy()

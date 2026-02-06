import time
import numpy as np
import matplotlib.pyplot as plt
from audio_processing.audio_stream import AudioStream

if __name__ == "__main__":
    stream = AudioStream()
    stream.start()
    plt.ion()
    fig, ax = plt.subplots()
    try:
        for _ in range(100):
            buf = stream.get_buffer()
            ax.cla()
            ax.plot(buf)
            ax.set_title("Live Audio Waveform")
            ax.set_xlabel("Sample")
            ax.set_ylabel("Amplitude")
            plt.pause(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        plt.ioff()
        plt.show()

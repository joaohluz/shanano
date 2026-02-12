import time
import matplotlib.pyplot as plt
from audio_processing.audio_stream import AudioStream

if __name__ == "__main__":

    stream = AudioStream()
    stream.start()
    fig, ax = plt.subplots()
    try:
        while True:
            #time.sleep(0.5)
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
        plt.close(fig)



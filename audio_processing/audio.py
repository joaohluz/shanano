from scipy.signal import butter, filtfilt
import librosa
import numpy as np

from config import DEFAULT_SR


def load_audio(path, sr=DEFAULT_SR):
    y, sr = librosa.load(path, sr=sr, mono=True)
    return y, sr


def record_audio(duration=7, sr=DEFAULT_SR):
    import sounddevice as sd
    audio = sd.rec(int(duration * sr), samplerate=sr, channels=1)
    sd.wait()
    return audio.flatten(), sr

def add_noise(y, noise_level=0.01):
    noise = np.random.normal(0, noise_level, len(y))
    return y + noise

def apply_filter(data, fs, order=5, btype='low', cutoff=None, lowcut=None, highcut=None):
    nyq = 0.5 * fs
    if btype in ['low', 'high']:
        normal_cutoff = cutoff / nyq
        b, a = butter(order, normal_cutoff, btype=btype, analog=False)
    elif btype == 'band':
        low = lowcut / nyq
        high = highcut / nyq
        b, a = butter(order, [low, high], btype='band')
    y = filtfilt(b, a, data)
    return y

def lowpass_filter(data, cutoff, fs, order=5):
    return apply_filter(data, fs, order, 'low', cutoff=cutoff)

def highpass_filter(data, cutoff, fs, order=5):
    return apply_filter(data, fs, order, 'high', cutoff=cutoff)

def bandpass_filter(data, lowcut, highcut, fs, order=5):
    return apply_filter(data, fs, order, 'band', lowcut=lowcut, highcut=highcut)

import numpy as np
import librosa
from scipy.ndimage import maximum_filter

from config import DEFAULT_AMP_MIN

def spectrogram(y, n_fft=4096, hop_length=512):
    S = librosa.stft(y, n_fft=n_fft, hop_length=hop_length)
    S = np.abs(S)
    S_db = librosa.amplitude_to_db(S, ref=np.max)
    return S_db

def find_peaks(S_db, amp_min=DEFAULT_AMP_MIN):
    neighborhood = maximum_filter(S_db, size=(20, 20))
    peaks = (S_db == neighborhood) & (S_db > amp_min)
    freqs, times = np.where(peaks)
    return list(zip(times, freqs))

def frame_to_seconds(frame, hop_length, sample_rate):
    return frame * hop_length / sample_rate

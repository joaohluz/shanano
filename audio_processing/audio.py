import librosa
import sounddevice as sd
import numpy as np
from config import DEFAULT_SR

def load_audio(path, sr=DEFAULT_SR):
    y, sr = librosa.load(path, sr=sr, mono=True)
    return y, sr

def record_audio(duration=7, sr=DEFAULT_SR):
    audio = sd.rec(int(duration * sr), samplerate=sr, channels=1)
    sd.wait()
    return audio.flatten(), sr

from pathlib import Path
import librosa

input_folder = Path("raw_wavs")

for wav_path in input_folder.glob("*.wav"):
    y, sr = librosa.load(wav_path.as_posix(), sr=None, mono=False)
    print(wav_path.name, y.shape, sr)

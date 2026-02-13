from pathlib import Path
import librosa
import soundfile as sf

INPUT_DIR = Path("data", "assets", "raw_wavs")
OUTPUT_DIR = Path("data", "assets", "clean_wavs")

TARGET_SR = 22050

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    wav_files = list(INPUT_DIR.glob("*.wav"))
    print(f"Found {len(wav_files)} wav files")

    for wav_path in wav_files:
        print(f"Processing {wav_path.name}...")

        y, sr = librosa.load(
            wav_path,
            sr=TARGET_SR,
            mono=True
        )

        out_path = OUTPUT_DIR / wav_path.name
        sf.write(out_path, y, TARGET_SR)

    print("Done.")

if __name__ == "__main__":
    main()

# Shanano: Audio Fingerprinting Song Matcher

Shanano is an exploratory project aimed at learning and implementing audio fingerprinting techniques for efficiently matching songs in a database. Inspired by Shazam's algorithm, this project demonstrates how to extract unique fingerprints from audio files and use them to identify songs from short recordings.

## How It Works

The system processes audio through several steps:

1. **Audio Loading**: Load WAV files and normalize them
2. **Spectrogram Generation**: Convert audio to time-frequency representation using STFT
3. **Peak Detection**: Find prominent spectral peaks above a threshold
4. **Fingerprint Generation**: Create unique hashes from peak pairs within time windows
5. **Database Storage**: Store fingerprints with song metadata
6. **Matching**: Compare query fingerprints against database to find matches

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/joaohluz/shanano.git
   cd shanano
   ```

2. Create a virtual environment:
   ```bash
   python -m venv shanano_venv
   source shanano_venv/bin/activate  # On Windows: shanano_venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Command Line Interface

The project provides a CLI with several commands:

- **List songs**: `python -m cli list`
- **Add songs**: `python -m cli add <path>` (path to WAV file or directory)
- **Match audio**: `python -m cli match --seconds [seconds]` (records and matches, default 7 seconds)
- **Live view**: `python -m cli live` (shows real-time audio waveform)

### Example Workflow

1. Add some songs to the database:
   ```bash
   python -m cli add data/assets/clean_wavs/
   ```

2. List the songs:
   ```bash
   python -m cli list
   ```

3. Play a song and match it:
   ```bash
   python -m cli match
   ```

## Notebooks

The project includes several Jupyter notebooks that provide detailed explanations and visualizations:

- **[audio_fingerprinting_pipeline.ipynb](audio_fingerprinting_pipeline.ipynb)**: Step-by-step explanation of the audio fingerprinting algorithm, including loading audio, computing spectrograms, detecting peaks, generating fingerprints, and matching against the database.

- **[Input_Audio_Pipeline.ipynb](Input_Audio_Pipeline.ipynb)**: Detailed walkthrough of the microphone audio processing pipeline, showing how recorded audio is processed through normalization, filtering, peak detection, and fingerprint generation.

- **[Input_Processing_Experiments.ipynb](Input_Processing_Experiments.ipynb)**: Experimental explorations of different audio processing techniques, parameter tuning, and performance analysis.

- **[perfect_match_histograms.ipynb](perfect_match_histograms.ipynb)**: Analysis of ideal matching scenarios with perfect audio alignment, demonstrating the effectiveness of the fingerprinting system.

These notebooks serve as educational resources and provide visual insights into each step of the audio fingerprinting process.

## Project Structure

- `audio_processing/`: Audio loading, spectrogram, and stream processing
- `controllers/`: Database operations, fingerprinting, and matching logic
- `tests/`: Unit tests
- `audio_pipeline.py`: Main fingerprinting pipeline
- `cli.py`: Command-line interface
- `*.ipynb`: Jupyter notebooks with detailed explanations and experiments

## Learning Objectives

This project explores:
- Digital signal processing concepts
- Audio feature extraction
- Database indexing for fast lookups
- Real-time audio processing

## Dependencies

The project uses minimal dependencies focused on audio processing and terminal interfaces. See `requirements.txt` for the complete list.

## License

This is an educational project. Feel free to explore and learn from the code!

The audio files I used in my experiments were obtained from the MUSAN audio collection. [MUSAN](https://openslr.org/17/) is a corpus of music, speech, and noise recordings supported by the National Science Foundation Graduate Research Fellowship under Grant No. 1232825 and by Spoken Communications.

```LaTeX
@misc{musan2015,
  author = {David Snyder and Guoguo Chen and Daniel Povey},
  title = {{MUSAN}: {A} {M}usic, {S}peech, and {N}oise {C}orpus},
  year = {2015},
  eprint = {1510.08484},
  note = {arXiv:1510.08484v1}
}
```

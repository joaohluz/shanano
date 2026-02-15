import numpy as np
from typing import Any, Dict, Optional

from audio_processing.audio import lowpass_filter
from audio_processing.spectrogram import spectrogram, find_peaks
from controllers.fingerprint import generate_fingerprints
from config import DEFAULT_AMP_MIN, DEFAULT_HOP_LENGTH, DEFAULT_LOWPASS_CUTOFF, DEFAULT_NOISE_FLOOR_DB, DEFAULT_SR

class AudioFingerprintPipeline:
    def __init__(self,
                 lowpass_cutoff: Optional[float] = DEFAULT_LOWPASS_CUTOFF,
                 noise_floor_db: float =  DEFAULT_NOISE_FLOOR_DB,
                 amp_min: float =  DEFAULT_AMP_MIN,
                 hop_length: int = DEFAULT_HOP_LENGTH,
                 sample_rate: int = DEFAULT_SR):
        self.lowpass_cutoff = lowpass_cutoff
        self.noise_floor_db = noise_floor_db
        self.amp_min = amp_min
        self.hop_length = hop_length
        self.sample_rate = sample_rate

        self.lowpass_filter = lowpass_filter
        self.spectrogram = spectrogram
        self.find_peaks = find_peaks
        self.generate_fingerprints = generate_fingerprints

    def run(self, y: np.ndarray):
        self.checkpoints: Dict[str, Any] = {}
        sr = self.sample_rate
        
        # Step 0: Store raw audio
        self.checkpoints['raw'] = y.copy()
        
        # Step 1: Normalize
        y_norm = y / np.max(np.abs(y)) * 0.95
        self.checkpoints['normalized'] = y_norm

        # Step 2: Filtering
        y_filt = y_norm
        y_filt = self.lowpass_filter(y_filt, self.lowpass_cutoff, sr)
        self.checkpoints['lowpass'] = y_filt
        
        # Step 3: Spectrogram
        S_db = self.spectrogram(y_filt)
        self.checkpoints['spectrogram'] = S_db

        # Step 4: Enhance spectrogram (apply noise floor)
        S_db_enhanced = np.maximum(S_db, self.noise_floor_db)
        self.checkpoints['enhanced'] = S_db_enhanced

        # Step 5: Find peaks
        peaks = self.find_peaks(S_db_enhanced, amp_min=self.amp_min)
        self.checkpoints['peaks'] = peaks

        # Step 6: Generate fingerprints
        fingerprints = self.generate_fingerprints(peaks)
        self.checkpoints['fingerprints'] = fingerprints

        return fingerprints

import numpy as np
import pytest

from audio_pipeline import AudioFingerprintPipeline
from config import DEFAULT_SR


@pytest.fixture
def pipeline():
    return AudioFingerprintPipeline()


@pytest.fixture
def sine_wave():
    duration = 2.0
    t = np.linspace(0, duration, int(DEFAULT_SR * duration), endpoint=False)
    return 0.5 * np.sin(2 * np.pi * 440 * t)


class TestAudioFingerprintPipeline:
    def test_checkpoints_populated(self, pipeline, sine_wave):
        result = pipeline.run(sine_wave)
        assert "raw" in pipeline.checkpoints
        assert "normalized" in pipeline.checkpoints
        assert "lowpass" in pipeline.checkpoints
        assert "spectrogram" in pipeline.checkpoints
        assert "enhanced" in pipeline.checkpoints
        assert "peaks" in pipeline.checkpoints
        assert "fingerprints" in pipeline.checkpoints

    def test_raw_audio_preserved(self, pipeline, sine_wave):
        pipeline.run(sine_wave)
        assert np.allclose(pipeline.checkpoints["raw"], sine_wave)

    def test_normalization(self, pipeline, sine_wave):
        pipeline.run(sine_wave)
        normalized = pipeline.checkpoints["normalized"]
        assert np.max(np.abs(normalized)) == pytest.approx(0.95, abs=1e-2)

    def test_returns_list_of_tuples(self, pipeline, sine_wave):
        result = pipeline.run(sine_wave)
        assert isinstance(result, list)
        if result:
            f = result[0]
            assert len(f) == 5
            h, anchor_time, anchor_freq, target_time, target_freq = f
            assert isinstance(h, str)
            assert len(h) == 20

    def test_spectrogram_is_2d_array(self, pipeline, sine_wave):
        pipeline.run(sine_wave)
        S_db = pipeline.checkpoints["spectrogram"]
        assert isinstance(S_db, np.ndarray)
        assert S_db.ndim == 2

    def test_peaks_are_time_freq_pairs(self, pipeline, sine_wave):
        pipeline.run(sine_wave)
        peaks = pipeline.checkpoints["peaks"]
        if peaks:
            t, f = peaks[0]
            assert isinstance(t, np.integer)
            assert isinstance(f, np.integer)

    def test_near_silence_does_not_crash(self, pipeline):
        silence = np.random.normal(0, 1e-10, int(DEFAULT_SR * 1.0))
        result = pipeline.run(silence)
        assert isinstance(result, list)

    @pytest.mark.parametrize("freq", [220, 440, 880])
    def test_different_frequencies_produce_fingerprints(self, freq, pipeline):
        duration = 2.0
        t = np.linspace(0, duration, int(DEFAULT_SR * duration), endpoint=False)
        y = 0.5 * np.sin(2 * np.pi * freq * t)
        result = pipeline.run(y)
        assert isinstance(result, list)

    def test_invalid_input_raises(self, pipeline):
        with pytest.raises(Exception):
            pipeline.run(np.array([]))

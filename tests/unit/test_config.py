import config


class TestConfig:
    def test_upload_dir_is_string(self):
        assert isinstance(config.UPLOAD_DIR, str)

    def test_fan_out_is_positive_int(self):
        assert isinstance(config.FAN_OUT, int)
        assert config.FAN_OUT > 0

    def test_time_delta_bounds(self):
        assert isinstance(config.MIN_TIME_DELTA, int)
        assert isinstance(config.MAX_TIME_DELTA, int)
        assert config.MIN_TIME_DELTA < config.MAX_TIME_DELTA

    def test_sample_rate_is_positive(self):
        assert isinstance(config.DEFAULT_SR, int)
        assert config.DEFAULT_SR > 0

    def test_hop_length_is_positive(self):
        assert isinstance(config.DEFAULT_HOP_LENGTH, int)
        assert config.DEFAULT_HOP_LENGTH > 0

    def test_n_fft_is_positive(self):
        assert isinstance(config.DEFAULT_N_FFT, int)
        assert config.DEFAULT_N_FFT > 0

    def test_amp_min_is_negative(self):
        assert isinstance(config.DEFAULT_AMP_MIN, (int, float))
        assert config.DEFAULT_AMP_MIN < 0

    def test_buffer_seconds_is_positive(self):
        assert isinstance(config.BUFFER_SECONDS, int)
        assert config.BUFFER_SECONDS > 0

    def test_chunk_size_is_positive(self):
        assert isinstance(config.CHUNK_SIZE, int)
        assert config.CHUNK_SIZE > 0

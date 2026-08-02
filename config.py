import os

UPLOAD_DIR = "data/uploads"

# Internet Archive catalog ingestion (Iteration 4)
CATALOG_COLLECTION = os.getenv("CATALOG_COLLECTION", "etree")
CATALOG_MAX_ITEMS = int(os.getenv("CATALOG_MAX_ITEMS", "5"))

IA_ADVANCED_SEARCH_URL = "https://archive.org/advancedsearch.php"
IA_METADATA_URL = "https://archive.org/metadata"
IA_IMG_URL = "https://archive.org/services/img"
IA_DOWNLOAD_URL = "https://archive.org/download"
IA_DETAILS_URL = "https://archive.org/details"

# Audio file extensions to pull from IA items, in preference order
# (lossless FLAC/OGG first, M4A/MP3 as fallback per Iteration 4 spec).
# Per track, the best-format member is kept; bitrate transcodes are collapsed.
CATALOG_AUDIO_EXTENSIONS = (".flac", ".ogg", ".m4a", ".mp3")

# Audio formats accepted by the upload/match endpoints (librosa decodes these).
SUPPORTED_AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg", ".m4a")

# Match acceptance thresholds: a candidate is only returned when it clears
# both a minimum offset-vote score and a minimum confidence (fraction of
# matched fingerprints voting for the winning offset). Keeps single spurious
# hash collisions (score 1) from producing false positives.
MATCH_MIN_SCORE = int(os.getenv("MATCH_MIN_SCORE", "2"))
MATCH_MIN_CONFIDENCE = float(os.getenv("MATCH_MIN_CONFIDENCE", "0.1"))

# Auth (Iteration 4, Phase 4.3)
# JWT_SECRET has NO default: it must come from the environment (never hardcode it).
# A RuntimeError is raised if a token is created/decoded without it.
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "1440"))

# Startup-seeded users. Defaults are local-dev only; set real credentials via env
# in any non-local deployment (docker-compose/k8s pass ADMIN_*/LOADGEN_* vars).
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
LOADGEN_USERNAME = os.getenv("LOADGEN_USERNAME", "loadgen")
LOADGEN_PASSWORD = os.getenv("LOADGEN_PASSWORD", "loadgen")

FAN_OUT = 15           # number of target peaks per anchor
MIN_TIME_DELTA = 1
MAX_TIME_DELTA = 200

# Audio Streaming parameters
DEFAULT_SR = 22050
DEFAULT_HOP_LENGTH = 512
DEFAULT_N_FFT = 2048
DEFAULT_AMP_MIN = -60
DEFAULT_NOISE_FLOOR_DB = -75
DEFAULT_LOWPASS_CUTOFF = 8000
BUFFER_SECONDS = 15
CHUNK_SIZE = 1024 

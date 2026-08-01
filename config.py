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
CATALOG_AUDIO_EXTENSIONS = (".flac", ".ogg", ".m4a", ".mp3")

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

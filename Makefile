# Shanano — demo targets (see demo.md for the full walkthrough)
# Each `make <target>` is a standalone command; env vars are set here so you
# don't need to `export` anything per terminal.

PYTHON    := .venv/bin/python
DB_FILE   := /tmp/shanano_demo.db
DATABASE_URL := sqlite+aiosqlite:////$(DB_FILE)
JWT_SECRET := demo-secret
BASE      := http://localhost:8000
COLLECTION := librivoxaudio
MAX_ITEMS := 1

export DATABASE_URL
export JWT_SECRET

.PHONY: help setup api worker catalog dedupe songs status \
        auth upload clip noise match negative cover \
        songs-catalog match-catalog clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- demo: full-stack ---

songs-catalog: ## END-TO-END: setup + API schema hint (run api first) + catalog fetch
	$(MAKE) catalog

match-catalog: ## END-TO-END: build clip from catalog audio and match it
	$(MAKE) clip
	$(MAKE) match

# --- terminal 1: services (long-running, one per terminal) ---

api: ## Start the API on :8000 (creates schema + seeds admin/loadgen)
	$(PYTHON) -m uvicorn api.main:app --port 8000

worker: ## Start the background fingerprinting worker
	$(PYTHON) worker.py

# --- terminal 2: catalog flow ---

setup: ## Reset the throwaway demo DB (fresh state)
	rm -f $(DB_FILE)
	@echo "demo DB reset"

catalog: ## Fetch one batch from the IA catalog (search -> download -> insert)
	$(PYTHON) catalog_fetch.py --collection $(COLLECTION) --max-items $(MAX_ITEMS)

dedupe: ## Re-run the catalog fetch to show dedupe ("already ingested, skipping")
	$(PYTHON) catalog_fetch.py --collection $(COLLECTION) --max-items $(MAX_ITEMS)

# --- terminal 2: inspect ---

songs: ## List songs (metadata) via the public API
	curl -s $(BASE)/songs/ | $(PYTHON) -m json.tool

status: ## Show id/status/fingerprint_count only
	curl -s $(BASE)/songs/ | $(PYTHON) -c \
	  "import sys,json; [print(s['id'], s['status'], s.get('fingerprint_count')) for s in json.load(sys.stdin)]"

songs-sql: ## Same, straight from the SQLite DB
	sqlite3 $(DB_FILE) "SELECT id, name, artist, year, status, source, source_url FROM songs;"

cover: ## Check the catalog song's cover-art URL responds
	curl -s -o /dev/null -w "cover-art: %{http_code}\n" \
	  "$$(sqlite3 $(DB_FILE) "SELECT cover_art_url FROM songs LIMIT 1;")"

# --- terminal 2: auth checks (section 1 of demo.md) ---

auth: ## Run the 8 auth checks (login/me/roles/protection)
	@echo "1) login admin ->"; curl -s $(BASE)/auth/login -d "username=admin&password=admin" \
	  -H "Content-Type: application/x-www-form-urlencoded"; echo
	@TOKEN=$$(curl -s $(BASE)/auth/login -d "username=admin&password=admin" \
	  -H "Content-Type: application/x-www-form-urlencoded" \
	  | $(PYTHON) -c "import sys,json;print(json.load(sys.stdin)['access_token'])") ; \
	echo "2) /auth/me ->"; curl -s $(BASE)/auth/me -H "Authorization: Bearer $$TOKEN"; echo ; \
	echo "3) tampered token ->"; curl -s -o /dev/null -w "%{http_code}\n" $(BASE)/auth/me -H "Authorization: Bearer $${TOKEN}k" ; \
	echo "4) admin registers alice ->"; curl -s -o /dev/null -w "%{http_code}\n" $(BASE)/auth/register \
	  -H "Authorization: Bearer $$TOKEN" -H "Content-Type: application/json" \
	  -d '{"username":"alice","password":"alicepw123"}' ; \
	echo "5) wrong password ->"; curl -s -o /dev/null -w "%{http_code}\n" $(BASE)/auth/login \
	  -d "username=admin&password=wrong" -H "Content-Type: application/x-www-form-urlencoded" ; \
	ALICE=$$(curl -s $(BASE)/auth/login -d "username=alice&password=alicepw123" \
	  -H "Content-Type: application/x-www-form-urlencoded" \
	  | $(PYTHON) -c "import sys,json;print(json.load(sys.stdin)['access_token'])") ; \
	echo "6) alice registers ->"; curl -s -o /dev/null -w "%{http_code}\n" $(BASE)/auth/register \
	  -H "Authorization: Bearer $$ALICE" -H "Content-Type: application/json" \
	  -d '{"username":"mallory","password":"mallory123"}' ; \
	echo "7) upload no-token ->"; curl -s -o /dev/null -w "%{http_code}\n" -X POST $(BASE)/songs/ ; \
	echo "   upload with-token ->"; curl -s -o /dev/null -w "%{http_code}\n" -X POST $(BASE)/songs/ \
	  -H "Authorization: Bearer $$TOKEN" ; \
	echo "8) public songs-list ->"; curl -s -o /dev/null -w "%{http_code}\n" $(BASE)/songs/ ; \
	echo "   public health ->"; curl -s -o /dev/null -w "%{http_code}\n" $(BASE)/health

# --- terminal 2: match flow (section 3 of demo.md) ---

clip: ## Build a 15s WAV clip from the catalog-downloaded audio
	$(PYTHON) scripts/demo_audio.py clip

noise: ## Generate a random-noise WAV (used for the negative match check)
	$(PYTHON) scripts/demo_audio.py noise

match: ## Match /tmp/clip.wav against the catalog (expect 200 + metadata)
	@TOKEN=$$(curl -s $(BASE)/auth/login -d "username=admin&password=admin" \
	  -H "Content-Type: application/x-www-form-urlencoded" \
	  | $(PYTHON) -c "import sys,json;print(json.load(sys.stdin)['access_token'])") ; \
	curl -s $(BASE)/match/ -H "Authorization: Bearer $$TOKEN" -F "file=@/tmp/clip.wav" \
	  | $(PYTHON) -m json.tool

negative: noise ## Negative match cases: noise=404, no-token=401, bad-format=400
	@TOKEN=$$(curl -s $(BASE)/auth/login -d "username=admin&password=admin" \
	  -H "Content-Type: application/x-www-form-urlencoded" \
	  | $(PYTHON) -c "import sys,json;print(json.load(sys.stdin)['access_token'])") ; \
	curl -s -o /dev/null -w "noise: %{http_code}\n" $(BASE)/match/ \
	  -H "Authorization: Bearer $$TOKEN" -F "file=@/tmp/noise.wav" ; \
	curl -s -o /dev/null -w "no-token: %{http_code}\n" -X POST $(BASE)/match/ \
	  -F "file=@/tmp/clip.wav" ; \
	curl -s -o /dev/null -w "bad-format: %{http_code}\n" $(BASE)/match/ \
	  -H "Authorization: Bearer $$TOKEN" -F "file=@/tmp/clip.wav;type=text/plain;filename=clip.txt"

# --- terminal 2: upload a local WAV as a song ---

upload: ## Upload data/assets/clean_wavs/*.wav as a song (authed)
	@TOKEN=$$(curl -s $(BASE)/auth/login -d "username=admin&password=admin" \
	  -H "Content-Type: application/x-www-form-urlencoded" \
	  | $(PYTHON) -c "import sys,json;print(json.load(sys.stdin)['access_token'])") ; \
	curl -s -X POST $(BASE)/songs/ -H "Authorization: Bearer $$TOKEN" \
	  -F "file=@data/assets/clean_wavs/music-hd-0001.wav" | $(PYTHON) -m json.tool

# --- misc ---

clean: ## Remove demo DB and temp clip/noise files
	rm -f $(DB_FILE) /tmp/clip.wav /tmp/noise.wav
	@echo "demo artifacts removed"

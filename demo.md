# Shanano — Manual Demo (no UI needed)

Copy-paste walkthrough to demo the project from the terminal. Uses a throwaway
SQLite database so you need no Docker/Postgres, and hits the **real** Internet
Archive over the network.

> For a normal run the API defaults to Postgres (`DATABASE_URL`), but for a demo
> we point everything at one local SQLite file. Both API and catalog CLI read the
> same `DATABASE_URL`, so they share the DB.

## 0. Setup

Create a throwaway DB. `export`ed vars don't carry across shells, so **each
terminal must set them again** — a missing `$DB` gives
`sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL`.

> **Tip:** a `Makefile` wraps all of the below into named targets (`make help`
> to list them). It sets `DATABASE_URL`/`JWT_SECRET`/`BASE` for you, so no
> per-terminal exports are needed. The commands below are the same ones the
> targets run, shown for the raw curl version.

```bash
source .venv/bin/activate
export DB=sqlite+aiosqlite:////tmp/shanano_demo.db
export BASE=http://localhost:8000
rm -f /tmp/shanano_demo.db
```

**Terminal 1 — start the API** (creates the schema + seeds `admin/admin`,
`loadgen/loadgen` on startup):

```bash
source .venv/bin/activate
export DB=sqlite+aiosqlite:////tmp/shanano_demo.db
DATABASE_URL=$DB JWT_SECRET=demo-secret uvicorn api.main:app --port 8000
```

**Terminal 2 — run the demos below:**

```bash
source .venv/bin/activate
export DB=sqlite+aiosqlite:////tmp/shanano_demo.db
export BASE=http://localhost:8000
```

### Makefile quick reference

Each target is a standalone command in its own terminal (they don't share env):

```bash
make setup        # reset the demo DB
make api          # start the API on :8000            (terminal 1)
make worker       # start the fingerprinting worker   (terminal 2/3)
make catalog      # fetch one IA batch (librivoxaudio, max 1)
make dedupe       # re-run catalog -> "already ingested, skipping"
make songs        # list songs w/ metadata (public API)
make status       # id/status/fingerprint_count only
make auth         # run the 8 auth checks
make clip         # cut a 15s clip from the catalog song
make match        # match the clip (public, no token — expect 200 + metadata)
make negative     # noise=404 / anon-match=200 / bad-format=400
make upload       # upload data/assets/clean_wavs/music-hd-0001.wav
make clean        # remove demo DB + temp clip/noise
```

Full flow: `make setup`, `make api` (terminal 1), `make catalog`, `make worker`
(terminal 2), wait for `make status` to show `completed`, then
`make clip` + `make match`.

---

## 1. Auth — JWT, roles, protected routes

```bash
# 1. Login as the seeded admin → expect JSON with access_token
curl -s $BASE/auth/login -d "username=admin&password=admin" \
  -H "Content-Type: application/x-www-form-urlencoded"; echo

# 2. Store the token, then GET /auth/me → expect {"id":1,"username":"admin","role":"admin",...}
TOKEN=$(curl -s $BASE/auth/login -d "username=admin&password=admin" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s $BASE/auth/me -H "Authorization: Bearer $TOKEN"; echo

# 3. A tampered token → expect 401
curl -s $BASE/auth/me -H "Authorization: Bearer ${TOKEN}k"; echo

# 4. Admin registers a new user → expect 201 + alice
curl -s -i $BASE/auth/register \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"alicepw123"}' | head -1

# 5. Wrong password → expect 401
curl -s -o /dev/null -w "%{http_code}\n" $BASE/auth/login \
  -d "username=admin&password=wrong" -H "Content-Type: application/x-www-form-urlencoded"

# 6. alice tries to register someone → expect 403 (register is admin-only)
ALICE=$(curl -s $BASE/auth/login -d "username=alice&password=alicepw123" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -o /dev/null -w "%{http_code}\n" $BASE/auth/register \
  -H "Authorization: Bearer $ALICE" -H "Content-Type: application/json" \
  -d '{"username":"mallory","password":"mallory123"}'

# 7. Route protection: no token → 401, with token → 422 (auth ok, file missing)
curl -s -o /dev/null -w "upload-no-token: %{http_code}\n" -X POST $BASE/songs/
curl -s -o /dev/null -w "upload-with-token: %{http_code}\n" -X POST $BASE/songs/ \
  -H "Authorization: Bearer $TOKEN"

# 8. Public endpoints stay open → both 200
curl -s -o /dev/null -w "songs-list: %{http_code}\n" $BASE/songs/
curl -s -o /dev/null -w "health: %{http_code}\n" $BASE/health
```

Expected summary: `access_token` (1), alice's profile (2), `401` (3), `201` (4),
`401` (5), `403` (6), `upload-no-token: 401` + `upload-with-token: 422` (7),
`songs-list: 200` + `health: 200` (8).

---

## 2. Catalog — fetching, processing, storing (Internet Archive)

This demonstrates the whole IA pipeline: **search → metadata → download →
DB insert**, with dedupe on re-run. We use the `librivoxaudio` collection with
`--max-items 1` so the download stays small (~3 MB). Swap in
`etree`/`--max-items 5` for the default live-music collection (bigger files).

### 2a. Show the upstream source is reachable (optional, raw IA API)

```bash
# Search API returns identifiers
curl -s "https://archive.org/advancedsearch.php?q=collection:librivoxaudio&fl%5B%5D=identifier&rows=1&page=1&output=json" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('found:', d['response']['numFound'], d['response']['docs'][0]['identifier'])"

# Metadata API returns creator/title/date + audio file list
curl -s "https://archive.org/metadata/waldbauernbuebel_1102_librivox" \
  | python3 -c "import sys,json; m=json.load(sys.stdin)['metadata']; print(m.get('title'), '|', m.get('creator'), '|', m.get('date'))"
```

### 2b. Fetch, process, and store one batch

> Each new terminal needs its own `export DB=...` (bash variables don't carry
> across shells). If `$DB` is empty you'll get
> `sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL`.

```bash
export DB=sqlite+aiosqlite:////tmp/shanano_demo.db
# Fetches from IA, picks the preferred audio file, downloads it into
# data/uploads/, extracts metadata, and inserts a Song(status=pending).
DATABASE_URL=$DB python catalog_fetch.py --collection librivoxaudio --max-items 1
```

Expected log lines (structured JSON):
- `"event": "catalog search returned"` — search step
- `"event": "catalog item ingested", "file_name": "...ogg", "title": "..."` — process + store step
- `"ingested": 1` — batch summary

### 2c. Prove it was stored

```bash
# The downloaded audio file is on disk
ls -lh data/uploads/
file data/uploads/*.ogg

# The Song row (with extracted metadata) is in the DB
sqlite3 /tmp/shanano_demo.db \
  "SELECT id, name, artist, year, status, source, source_url, cover_art_url FROM songs;"

# And via the public API (metadata columns now populated)
curl -s $BASE/songs/ | python3 -m json.tool
```

### 2d. Prove dedupe — run the batch again

```bash
export DB=sqlite+aiosqlite:////tmp/shanano_demo.db
DATABASE_URL=$DB python catalog_fetch.py --collection librivoxaudio --max-items 1
```

Expected: `"event": "catalog item already ingested, skipping"` and `"ingested": 0`
— the same `source_url` is not re-imported.

### 2e. Optional — the cover art URL is live

```bash
curl -s -o /dev/null -w "cover-art: %{http_code}\n" \
  "$(sqlite3 /tmp/shanano_demo.db "SELECT cover_art_url FROM songs LIMIT 1;")"
# browse it: open <cover_art_url> in a browser
```

### 2f. Optional — see the worker fingerprint it

The catalog inserts songs as `pending`. Run the background worker (same DB) and
watch status flip `pending → processing → processed`:

```bash
export DB=sqlite+aiosqlite:////tmp/shanano_demo.db
# Terminal 3
DATABASE_URL=$DB python worker.py
```

Then poll the status:

```bash
watch -n 2 "curl -s $BASE/songs/ | python3 -m json.tool"
# or
sqlite3 /tmp/shanano_demo.db "SELECT name, status FROM songs;"
```

---

## 3. Match — real audio matching

This section matches a query clip against the catalog. It assumes section 2 ran
and the worker finished fingerprinting the song (status `completed`; ~30s for a
5-minute track). A fresh start is simplest:

```bash
# Terminal 1
source .venv/bin/activate
export DB=sqlite+aiosqlite:////tmp/shanano_demo.db
DATABASE_URL=$DB JWT_SECRET=demo-secret uvicorn api.main:app --port 8000

# Terminal 2
source .venv/bin/activate
export DB=sqlite+aiosqlite:////tmp/shanano_demo.db
export BASE=http://localhost:8000
DATABASE_URL=$DB python catalog_fetch.py --collection librivoxaudio --max-items 1

# Terminal 3 — worker fingerprints the pending song
source .venv/bin/activate
export DB=sqlite+aiosqlite:////tmp/shanano_demo.db
DATABASE_URL=$DB python worker.py
```

Wait until `curl -s $BASE/songs/` shows `"status": "completed"` (a 5-min track
takes ~30s to fingerprint). Then, in **Terminal 2**:

### 3a. Build a query clip from the downloaded song

```bash
# Cut the first 15 seconds of the downloaded track into a WAV clip
# (or just: make clip)
python3 scripts/demo_audio.py clip
```

The helper reads the catalog song's actual `file_path` from the DB (the most
recently completed song), so it always clips the right file even if other audio
sits in `data/uploads/`.

### 3b. Match it (public — no token needed)

`POST /match/` is now **public** (see `docs/webapp.md`): the mic-only webapp
matches anonymously, so the demo needs no login either.

```bash
curl -s $BASE/match/ \
  -F "file=@/tmp/clip.wav" | python3 -m json.tool
```

Expected: the song that the clip came from, with full metadata (artist, year,
genre, cover art URL, source URL) plus `score` and `confidence`
(score > 0, 0 < confidence ≤ 1).

### 3c. Negative cases

```bash
# Random noise must NOT match → expect 404 (thresholds reject weak hits)
python3 scripts/demo_audio.py noise   # or: make noise
curl -s -o /dev/null -w "noise: %{http_code}\n" $BASE/match/ \
  -F "file=@/tmp/noise.wav"                                   # 404

# Anonymous match works → expect 200 (endpoint is public, no Bearer header)
curl -s -o /dev/null -w "anon-match: %{http_code}\n" $BASE/match/ \
  -F "file=@/tmp/clip.wav"                                    # 200

# Unsupported extension → expect 400
curl -s -o /dev/null -w "bad-format: %{http_code}\n" $BASE/match/ \
  -F "file=@/tmp/clip.wav;type=text/plain;filename=clip.txt"  # 400
```

Expected: `noise: 404`, `anon-match: 200`, `bad-format: 400`.

---

## 4. Cleanup

```bash
# Stop the API (Ctrl-C) and worker (Ctrl-C)
rm -f /tmp/shanano_demo.db /tmp/clip.wav /tmp/noise.wav
# optionally remove downloaded files: rm -f data/uploads/*.ogg data/uploads/*.flac
```

---

## Notes

- Requires `aiosqlite` (in `requirements-dev.txt`) and network access to
  `archive.org`.
- The catalog CLI uses the same `DATABASE_URL` as the API; the API must have
  started once first so the schema exists (or run `alembic upgrade head`).
- **`make setup` / deleting the DB does NOT reset a running API.** The running
  process keeps an open file descriptor to the old (unlinked) SQLite file and
  will keep serving stale data. Stop the API and worker first, then reset and
  restart:
  ```bash
  pkill -f "uvicorn api.main:app"; pkill -f "worker.py"
  make setup
  make api    # fresh schema + seeded users
  ```
- A match returns a candidate only when it clears both thresholds: `score >= 2`
  and `confidence >= 0.2` (tunable via `MATCH_MIN_SCORE` / `MATCH_MIN_CONFIDENCE`).
- Only the terminal demo is shown here. A mic-only web UI (no login, no file
  upload) that calls `POST /match/` anonymously is specified in
  `docs/webapp.md` — the endpoints it calls are the ones above.

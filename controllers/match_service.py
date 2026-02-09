import queue
import threading
from rich import print
from collections import defaultdict
from controllers.database import connect, init_db

class MatchService:
    def __init__(self):
        self.match_found = threading.Event()
        self.match_result = None
        self.fingerprint_queue = queue.Queue()

    def submit_fingerprints(self, fps):
        self.fingerprint_queue.put(fps)

    def run(self):
        self.conn = connect()
        init_db(self.conn)
        while not self.match_found.is_set():
            try:
                fps = self.fingerprint_queue.get(timeout=0.1)
                if not fps:
                    continue
                print(f"Fingerprints batch size: {len(fps)}")
                result = self.match_fingerprints(fps)
                print(f"Returned result: {result}")
                if result:
                    self.match_result = result
                    self.match_found.set()
            except queue.Empty:
                continue

    def match_fingerprints(self, fingerprints):
        cur = self.conn.cursor()
        matches = defaultdict(list)

        print(f"Recognizing audio from {len(fingerprints)} fingerprints...")

        cur.execute("SELECT COUNT(*) FROM songs")
        total_songs = cur.fetchone()[0]
        print(f"Total songs in DB: {total_songs}")

        for h, offset in fingerprints:
            cur.execute(
                "SELECT name as song_name, offset FROM fingerprints LEFT JOIN songs ON (songs.id = fingerprints.song_id) WHERE hash=?",
                (h,)
            )
            for song_name, db_offset in cur.fetchall():
                # Convert db_offset to int
                matches[song_name].append(int(db_offset) - offset)

        scores = {}
        for song_name, offsets in matches.items():
            hist = defaultdict(int)
            for o in offsets:
                hist[o] += 1
            scores[song_name] = max(hist.values())
        chosen = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        print(f"Best match: {chosen[0][0]} with score {chosen[0][1]}")
        if chosen and chosen[0][1] > 50:
            return chosen[0]
        return None

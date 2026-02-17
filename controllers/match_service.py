import queue
import threading
from rich import print
from collections import defaultdict
from controllers.database import connect

class MatchService:
    def __init__(self, conn):
        self.match_found = threading.Event()
        self.match_result = None
        self.fingerprint_queue = queue.Queue()
        self.conn = conn

    def submit_fingerprints(self, fps):
        self.fingerprint_queue.put(fps)

    def run(self):
        self.conn = connect()
        while not self.match_found.is_set():
            try:
                fps = self.fingerprint_queue.get(timeout=0.1)
                if not fps:
                    continue
                print(f"Fingerprints batch size: {len(fps)}")
                match, offset_hist = self.match_fingerprints(fps)
                print(f"Returned result: {match}")
                if match:
                    self.match_result = match
                    self.match_found.set()
            except queue.Empty:
                continue

    def match_fingerprints(self, fingerprints):
        cur = self.conn.cursor()
        matches = defaultdict(list)
        for h, anchor_time, anchor_freq, target_time, target_freq in fingerprints:
            cur.execute(
                "SELECT name as song_name, anchor_time FROM fingerprints LEFT JOIN songs ON (songs.id = fingerprints.song_id) WHERE hash=?",
                (h,)
            )
            for song_name, db_anchor_time in cur.fetchall():
                matches[song_name].append(int(db_anchor_time) - anchor_time)

        song_candidates = []
        offset_count_per_song = {}
        for song_name, offsets in matches.items():
            hist = defaultdict(int)
            for o in offsets:
                hist[o] += 1
            score = max(hist.values())
            total_matches = sum(hist.values())
            song_candidates.append((song_name, score, total_matches))
            offset_count_per_song[song_name] = hist
        try:
            chosen = sorted(song_candidates, key=lambda x: (x[1], x[2]), reverse=True)
            best_song = chosen[0]
            return (best_song[0], best_song[1]) , offset_count_per_song[best_song[0]]
        except Exception as e:
            return None, None

    def get_matching_fingerprints_in_song(self, song_name, fps):
        cur = self.conn.cursor()
        hashes = [h for h, _, _, _, _ in fps]
        placeholders = ','.join(['?'] * len(hashes))
        query = f"SELECT hash, anchor_time, anchor_freq, target_time, target_freq FROM fingerprints LEFT JOIN songs ON (songs.id = fingerprints.song_id) WHERE song_id=(SELECT id FROM songs WHERE name=?) AND hash IN ({placeholders})"
        cur.execute(query, (song_name, *hashes))
        return cur.fetchall()

from collections import defaultdict

def recognize(conn, fingerprints):
    cur = conn.cursor()
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

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)

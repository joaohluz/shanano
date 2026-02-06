from rich import print
from collections import defaultdict
from audio_processing.audio import record_audio
from audio_processing.spectrogram import spectrogram, find_peaks
from controllers.fingerprint import generate_fingerprints



def match(conn):
    print(f"\n[yellow] Starting recording...[/yellow]")
    
    y_mic, sr_mic = record_audio(duration=7)
    print(f"\r[yellow] Recording done. Processing...[/yellow]")
    
    S_db_mic = spectrogram(y_mic, sr_mic)
    print(f"\r[yellow] Spectrogram computed. Finding peaks...[/yellow]")
    
    peaks_mic = find_peaks(S_db_mic)
    print(f"\r[yellow] Found {len(peaks_mic)} peaks. Generating fingerprints...[/yellow]")

    fps_mic = generate_fingerprints(peaks_mic)
    print(f"\r[yellow] Generated {len(fps_mic)} fingerprints. Matching against DB...[/yellow]")

    matches = match_fingerprints(conn, fps_mic)
    return matches
    

def match_fingerprints(conn, fingerprints):
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

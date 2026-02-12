import hashlib
from config import FAN_OUT, MIN_TIME_DELTA, MAX_TIME_DELTA

def generate_fingerprints(peaks):
    fingerprints = []

    for i, anchor in enumerate(peaks):
        t1, f1 = anchor

        for target in peaks[i+1:i+1+FAN_OUT]:
            t2, f2 = target
            delta_t = t2 - t1

            if MIN_TIME_DELTA <= delta_t <= MAX_TIME_DELTA:
                h = hash_peak_pair(f1, f2, delta_t)
                fingerprints.append((h, t1, f1, t2, f2))

    return fingerprints

def hash_peak_pair(f1, f2, delta_t):
    s = f"{f1}|{f2}|{delta_t}"
    return hashlib.sha1(s.encode()).hexdigest()[:20]

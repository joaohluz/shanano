"""Demo helpers used by the Makefile (build match clips, noise, etc.)."""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import soundfile as sf
from sqlalchemy import select

from audio_processing.audio import load_audio
from core.database import async_session
from core.models import ProcessingStatus, Song


def _catalog_audio_path() -> str:
    """Path of a completed catalog song (most recently fingerprinted)."""
    async def _fetch() -> str:
        async with async_session() as db:
            result = await db.execute(
                select(Song.file_path)
                .where(Song.status == ProcessingStatus.completed)
                .order_by(Song.id.desc())
                .limit(1)
            )
            path = result.scalar_one_or_none()
            if not path:
                raise SystemExit(
                    "no completed catalog song found — run: make catalog, then make worker"
                )
            return path

    return asyncio.run(_fetch())


def make_clip(duration: float = 15.0, out_path: str = "/tmp/clip.wav") -> None:
    """Cut the first ``duration`` seconds of the catalog-downloaded audio to a WAV."""
    path = _catalog_audio_path()
    y, sr = load_audio(path)
    clip = y[: int(duration * sr)]
    sf.write(out_path, clip, sr)
    print(f"clip written: {len(clip) / sr:.1f}s -> {out_path} (from {Path(path).name})")


def make_noise(duration: float = 5.0, out_path: str = "/tmp/noise.wav") -> None:
    """Write random white noise (used to check the no-match 404 path)."""
    rng = np.random.default_rng(1)
    sf.write(out_path, rng.standard_normal(int(22050 * duration)), 22050)
    print(f"noise written: {duration}s -> {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Shanano demo audio helpers")
    parser.add_argument("kind", choices=["clip", "noise"])
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if args.kind == "clip":
        make_clip(args.duration, args.out or "/tmp/clip.wav")
    else:
        make_noise(args.duration, args.out or "/tmp/noise.wav")


if __name__ == "__main__":
    main()

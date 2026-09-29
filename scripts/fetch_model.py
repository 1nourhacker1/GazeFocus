"""Download the MediaPipe face landmarker model and verify its SHA-256."""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
DEST = Path(__file__).resolve().parents[1] / "models" / "face_landmarker.task"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if DEST.exists() and sha256_of(DEST) == SHA256:
        print(f"model ok: {DEST}")
        return 0
    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_suffix(".part")
    urllib.request.urlretrieve(URL, tmp)
    got = sha256_of(tmp)
    if got != SHA256:
        tmp.unlink()
        print(f"hash mismatch: got {got}, expected {SHA256}", file=sys.stderr)
        return 1
    tmp.replace(DEST)
    print(f"model downloaded: {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

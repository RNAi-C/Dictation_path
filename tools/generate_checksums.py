"""
generate_checksums.py
Run from the portable folder root after packaging:
    runtime\python\python.exe tools\generate_checksums.py

Generates SHA-256 checksums for all files in the portable folder
and writes them to checksums/SHA256SUMS.txt.
"""

import hashlib
import sys
from pathlib import Path

PORTABLE_ROOT = Path(__file__).resolve().parent.parent
CHECKSUM_FILE = PORTABLE_ROOT / "checksums" / "SHA256SUMS.txt"

# Directories to skip (logs, temp, __pycache__)
SKIP_DIRS = {"__pycache__", ".cache", "logs", "data", "checksums", "audio"}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    print(f"Generating checksums for: {PORTABLE_ROOT}")
    CHECKSUM_FILE.parent.mkdir(exist_ok=True)

    entries = []
    for p in sorted(PORTABLE_ROOT.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p == CHECKSUM_FILE:
            continue
        rel = p.relative_to(PORTABLE_ROOT).as_posix()
        digest = sha256(p)
        entries.append(f"{digest}  {rel}")
        print(f"  {digest[:16]}...  {rel}")

    CHECKSUM_FILE.write_text("\n".join(entries) + "\n", encoding="utf-8")
    print(f"\nWrote {len(entries)} checksums to {CHECKSUM_FILE.relative_to(PORTABLE_ROOT)}")

if __name__ == "__main__":
    main()

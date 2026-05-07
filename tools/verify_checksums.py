"""
verify_checksums.py
Run from the portable folder root on the TARGET computer:
    runtime\python\python.exe tools\verify_checksums.py

Verifies SHA-256 checksums against checksums/SHA256SUMS.txt.
Reports any modified, missing, or extra files.
"""

import hashlib
import sys
from pathlib import Path

PORTABLE_ROOT = Path(__file__).resolve().parent.parent
CHECKSUM_FILE = PORTABLE_ROOT / "checksums" / "SHA256SUMS.txt"

SKIP_DIRS = {"__pycache__", ".cache", "logs", "data", "checksums", "audio"}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    if not CHECKSUM_FILE.exists():
        print(f"ERROR: {CHECKSUM_FILE} not found — run generate_checksums.py first")
        sys.exit(1)

    expected: dict[str, str] = {}
    for line in CHECKSUM_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, rel_path = line.split("  ", 1)
        expected[rel_path] = digest

    print(f"Verifying {len(expected)} files in {PORTABLE_ROOT}")
    errors = 0

    for rel, exp_digest in sorted(expected.items()):
        full = PORTABLE_ROOT / rel
        if not full.exists():
            print(f"[ MISSING ] {rel}")
            errors += 1
            continue
        got = sha256(full)
        if got != exp_digest:
            print(f"[ CHANGED ] {rel}")
            errors += 1

    if errors == 0:
        print(f"\nAll {len(expected)} files verified OK.")
    else:
        print(f"\n{errors} file(s) failed verification — package may be corrupted.")
    sys.exit(0 if errors == 0 else 1)

if __name__ == "__main__":
    main()

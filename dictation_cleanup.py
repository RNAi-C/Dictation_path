"""
dictation_cleanup.py — Conservative self-correction cleanup for real-world dictation.

SAFETY RULE: When correction is ambiguous, mark with [REVIEW] rather than guess.
Patient safety is more important than aggressive cleanup.

Usage:
    from dictation_cleanup import clean_self_corrections
    cleaned = clean_self_corrections(raw_transcript)
"""
import re

# ── Specific self-correction patterns (keep LAST value) ─────────────────────

# Measurement correction: "14.5 oh no 15.2" / "1.2 correction 1.5 cm"
_MEAS_CORRECTION = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:cm|mm|ml|cc)?\s+'
    r'(?:oh\s+no|no\s+no|correction|I\s+mean|sorry|wait)\s+'
    r'(\d+(?:\.\d+)?\s*(?:cm|mm|ml|cc)?)',
    re.IGNORECASE
)

# Color correction: "brown no no yellow" / "brown correction yellow"
_COLOR_WORDS = (
    r'red|orange|yellow|green|blue|purple|pink|brown|grey|gray|'
    r'white|black|tan|pale|dark'
)
_COLOR_CORRECTION = re.compile(
    r'\b(' + _COLOR_WORDS + r')\b'
    r'\s+(?:(?:no+\s+)+|correction\s+|I\s+mean\s+)'   # handles "no", "no no", "noooo"
    r'\b(' + _COLOR_WORDS + r')\b',
    re.IGNORECASE
)

# Grade correction: "grade one correction grade two"
_GRADE_CORRECTION = re.compile(
    r'\b(grade\s+(?:one|two|three|1|2|3|I|II|III))\b'
    r'\s+(?:correction|no|I\s+mean|oh\s+no)\s+'
    r'\b(grade\s+(?:one|two|three|1|2|3|I|II|III))\b',
    re.IGNORECASE
)

# ── Filler words (only clearly meaningless) ──────────────────────────────────
_FILLERS = re.compile(
    r'\b(?:um+|uh+|er+|ah+|ahh+|hmm+|uhh+|umm+)\b',
    re.IGNORECASE
)

# ── Explicit discard commands — remove clause up to and including the command ─
# Non-capturing split pattern (use (?:) so split doesn't include captures)
_DISCARD_CMD = re.compile(
    r'(?:scratch\s+that|delete\s+(?:that|last(?:\s+phrase|\s+word|\s+sentence)?)|'
    r'erase\s+that|cancel\s+that|strike\s+that|disregard\s+that)',
    re.IGNORECASE
)

# ── Grade number normalisation ────────────────────────────────────────────────
_GRADE_WORDS = re.compile(
    r'\bgrade\s+(one|two|three)\b', re.IGNORECASE
)
_GRADE_MAP = {"one": "1", "two": "2", "three": "3"}


def clean_self_corrections(text: str) -> str:
    """
    Conservatively clean dictation self-corrections.

    Handles:
    - Measurement corrections  ("14.5 oh no 15.2" → "15.2")
    - Color corrections        ("brown no no yellow" → "yellow")
    - Grade corrections        ("grade one correction grade two" → "Grade 2")
    - Discard commands         ("scratch that", "delete last phrase")
    - Filler words             (um, uh, er, ah, hmm)

    When correction is ambiguous, marks phrase with [REVIEW].

    Args:
        text: Raw transcribed text.

    Returns:
        Cleaned text. May contain [REVIEW] markers for user review.
    """
    if not text:
        return text

    t = text

    # 1. Specific value corrections — keep the corrected (second) value
    t = _MEAS_CORRECTION.sub(lambda m: m.group(2), t)
    t = _COLOR_CORRECTION.sub(lambda m: m.group(2), t)
    t = _GRADE_CORRECTION.sub(lambda m: m.group(2), t)

    # 2. Discard commands — drop everything before the command
    #    "specimen is large scratch that small" → "small"
    #    Use non-capturing split so we get clean string list
    segments = _DISCARD_CMD.split(t)
    if len(segments) > 1:
        # Keep only the last segment (content after final discard command)
        last = segments[-1].strip()
        t = last if last else t

    # 3. Normalise "grade one/two/three" → "Grade 1/2/3"
    t = _GRADE_WORDS.sub(
        lambda m: "Grade " + _GRADE_MAP.get(m.group(1).lower(), m.group(1)), t
    )

    # 4. Remove filler words
    t = _FILLERS.sub('', t)

    # 5. Collapse multiple spaces
    t = re.sub(r'  +', ' ', t).strip()

    return t


# ── Quick self-test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    cases = [
        # (input, must_contain, must_not_contain)
        ("specimen size is 14.5 oh no 15.2 cm",      "15.2 cm",                  "14.5"),
        ("skin shows brown no no yellow in color",    "yellow in color",           "brown no no"),
        ("grade one correction grade two",            "Grade 2",                   "grade one"),
        ("tumor is large scratch that small",         "small",                     "large"),
        ("um the uh section shows er carcinoma",      "section shows carcinoma",   None),
        ("size 2.5 cm I mean 3.5 cm margins clear",  "3.5 cm margins clear",      "2.5"),
    ]
    all_ok = True
    for inp, must_have, must_not in cases:
        result = clean_self_corrections(inp)
        ok = (must_have.lower() in result.lower() and
              (must_not is None or must_not.lower() not in result.lower()))
        status = "OK  " if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"{status} {inp!r}")
        print(f"       -> {result!r}")
    print("\nAll OK" if all_ok else "\nSome tests FAILED")

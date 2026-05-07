"""
Terminology correction module for Pathology Dictation Assistant.
Applies custom pathology term replacements to transcribed text.
"""

import json
import re
from pathlib import Path
from typing import Dict, Optional
from loguru import logger

from config import DictionaryConfig


class TerminologyCorrector:
    """Applies pathology terminology corrections to text."""

    def __init__(self, config: DictionaryConfig, dictionary_path: Path):
        self.config = config
        self.dictionary_path = dictionary_path
        self.replacements = {}

        if config.enabled:
            self._load_dictionary()
        else:
            logger.info("Terminology correction is disabled")

    def _load_dictionary(self) -> None:
        """Load terminology dictionary from JSON file."""
        if not self.dictionary_path.exists():
            logger.info(f"Dictionary file not found: {self.dictionary_path}")
            logger.info("Creating empty dictionary template...")
            self._create_default_dictionary()

        try:
            with open(self.dictionary_path, 'r', encoding='utf-8') as f:
                self.replacements = json.load(f)

            logger.info(f"Loaded {len(self.replacements)} terminology replacements")

        except Exception as e:
            logger.error(f"Failed to load dictionary: {e}")
            self.replacements = {}

    def _create_default_dictionary(self) -> None:
        """Create a default dictionary with examples."""
        default_dict = {
            "doctor carcinoma": "ductal carcinoma",
            "usual doctor hyperplasia": "usual ductal hyperplasia",
            "hurt two": "HER2",
            "key sixty seven": "Ki-67",
            "p sixty three": "p63",
            "men in geoma": "meningioma",
            "mucinous adenocarcinoma": "mucinous adenocarcinoma",
            "grade one": "Grade 1",
            "grade two": "Grade 2",
            "grade three": "Grade 3",
        }

        try:
            self.dictionary_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.dictionary_path, 'w', encoding='utf-8') as f:
                json.dump(default_dict, f, indent=2, ensure_ascii=False)

            logger.info(f"Created default dictionary at {self.dictionary_path}")
            self.replacements = default_dict

        except Exception as e:
            logger.error(f"Failed to create default dictionary: {e}")

    def add_replacement(self, incorrect: str, correct: str) -> None:
        """
        Add a new term replacement.

        Args:
            incorrect: common speech-to-text error or approximation
            correct: correct pathology terminology
        """
        self.replacements[incorrect] = correct

    def save_dictionary(self) -> None:
        """Save current dictionary to file."""
        try:
            self.dictionary_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.dictionary_path, 'w', encoding='utf-8') as f:
                json.dump(self.replacements, f, indent=2, ensure_ascii=False)

            logger.info(f"Dictionary saved: {len(self.replacements)} replacements")

        except Exception as e:
            logger.error(f"Failed to save dictionary: {e}")

    def correct(self, text: str) -> str:
        """
        Apply terminology corrections to text.

        Args:
            text: transcribed text to correct

        Returns:
            Corrected text
        """
        if not self.config.enabled or not text:
            return text

        corrected_text = text

        for incorrect, correct in self.replacements.items():
            if self.config.case_sensitive:
                # Case-sensitive replacement
                corrected_text = corrected_text.replace(incorrect, correct)
            else:
                # Case-insensitive replacement using regex
                # This preserves the original case pattern when possible
                pattern = re.compile(re.escape(incorrect), re.IGNORECASE)
                corrected_text = pattern.sub(correct, corrected_text)

        return corrected_text

    def correct_with_logging(self, text: str) -> tuple[str, list]:
        """
        Apply corrections and log which replacements were made.

        Args:
            text: transcribed text to correct

        Returns:
            Tuple of (corrected_text, list_of_replacements_made)
        """
        if not self.config.enabled or not text:
            return text, []

        replacements_made = []
        corrected_text = text

        for incorrect, correct in self.replacements.items():
            if self.config.case_sensitive:
                if incorrect in corrected_text:
                    count = corrected_text.count(incorrect)
                    corrected_text = corrected_text.replace(incorrect, correct)
                    replacements_made.append({
                        'original': incorrect,
                        'replacement': correct,
                        'count': count
                    })
            else:
                pattern = re.compile(re.escape(incorrect), re.IGNORECASE)
                matches = pattern.findall(corrected_text)
                if matches:
                    corrected_text = pattern.sub(correct, corrected_text)
                    replacements_made.append({
                        'original': incorrect,
                        'replacement': correct,
                        'count': len(matches)
                    })

        logger.info(f"Applied {len(replacements_made)} terminology corrections")
        for replacement in replacements_made:
            logger.debug(
                f"  {replacement['original']} -> {replacement['replacement']} "
                f"(count: {replacement['count']})"
            )

        return corrected_text, replacements_made

    def get_dictionary(self) -> Dict[str, str]:
        """Get current replacement dictionary."""
        return self.replacements.copy()

    def clear_dictionary(self) -> None:
        """Clear all replacements."""
        self.replacements = {}


if __name__ == "__main__":
    # Simple test
    from config import PathologyDictationConfig

    cfg = PathologyDictationConfig()
    corrector = TerminologyCorrector(cfg.dictionary, cfg.dictionary_path)

    test_text = "The biopsy shows doctor carcinoma with key sixty seven expression at 40%"
    corrected, replacements = corrector.correct_with_logging(test_text)

    print(f"Original: {test_text}")
    print(f"Corrected: {corrected}")
    print(f"Replacements: {replacements}")

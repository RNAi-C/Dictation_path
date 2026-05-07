"""
Clipboard handler for Pathology Dictation Assistant.
Manages copying text to system clipboard with encoding safety.
"""

import pyperclip
from loguru import logger


class ClipboardHandler:
    """Handles clipboard operations safely."""

    @staticmethod
    def copy_to_clipboard(text: str) -> bool:
        """
        Copy text to system clipboard.

        Args:
            text: text to copy

        Returns:
            True if successful, False otherwise
        """
        if not text:
            logger.warning("Attempted to copy empty text to clipboard")
            return False

        try:
            # pyperclip handles encoding automatically
            pyperclip.copy(text)
            logger.info(f"Copied {len(text)} characters to clipboard")
            return True

        except Exception as e:
            logger.error(f"Failed to copy to clipboard: {e}")
            return False

    @staticmethod
    def get_clipboard() -> str:
        """
        Get current clipboard contents.

        Returns:
            Clipboard text, or empty string if failed
        """
        try:
            text = pyperclip.paste()
            logger.debug(f"Retrieved {len(text)} characters from clipboard")
            return text

        except Exception as e:
            logger.error(f"Failed to read clipboard: {e}")
            return ""

    @staticmethod
    def clear_clipboard() -> bool:
        """
        Clear clipboard contents.

        Returns:
            True if successful, False otherwise
        """
        try:
            pyperclip.copy("")
            logger.info("Clipboard cleared")
            return True

        except Exception as e:
            logger.error(f"Failed to clear clipboard: {e}")
            return False


if __name__ == "__main__":
    # Simple test
    handler = ClipboardHandler()

    test_text = "This is a test of the clipboard handler"
    success = handler.copy_to_clipboard(test_text)
    print(f"Copy successful: {success}")

    retrieved = handler.get_clipboard()
    print(f"Retrieved text: {retrieved}")
    print(f"Match: {test_text == retrieved}")

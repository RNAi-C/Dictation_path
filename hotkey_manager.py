"""
Hotkey manager for Pathology Dictation Assistant.
Handles keyboard shortcut detection and callbacks.
"""

import keyboard
from typing import Callable, Optional
from loguru import logger

from config import HotkeyConfig


class HotkeyManager:
    """Manages hotkey registration and callbacks."""

    def __init__(self, config: HotkeyConfig):
        self.config = config
        self.is_recording = False
        self.on_toggle_record: Optional[Callable] = None
        self._listener_id = None

        self._register_hotkeys()

    def _register_hotkeys(self) -> None:
        """Register all configured hotkeys."""
        try:
            logger.info(f"Registering hotkey: {self.config.toggle_record}")

            # Register the hotkey
            self._listener_id = keyboard.on_press_key(
                self.config.toggle_record,
                self._on_toggle_record_pressed
            )

            logger.info(f"Hotkey registered successfully: {self.config.toggle_record}")

        except Exception as e:
            logger.error(f"Failed to register hotkeys: {e}")
            raise

    def _on_toggle_record_pressed(self, event) -> None:
        """Internal callback for toggle record hotkey."""
        if self.on_toggle_record:
            try:
                self.on_toggle_record()
            except Exception as e:
                logger.error(f"Error in toggle_record callback: {e}")

    def set_toggle_record_callback(self, callback: Callable) -> None:
        """
        Set the callback function for the toggle record hotkey.

        Args:
            callback: function to call when hotkey is pressed
        """
        self.on_toggle_record = callback
        logger.info("Toggle record callback registered")

    def unregister_hotkeys(self) -> None:
        """Unregister all hotkeys."""
        try:
            if self._listener_id:
                keyboard.remove_hotkey(self._listener_id)
            logger.info("Hotkeys unregistered")

        except Exception as e:
            logger.error(f"Failed to unregister hotkeys: {e}")

    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.unregister_hotkeys()
        except:
            pass


if __name__ == "__main__":
    # Simple test
    from config import PathologyDictationConfig

    cfg = PathologyDictationConfig()
    manager = HotkeyManager(cfg.hotkey)

    call_count = 0

    def test_callback():
        global call_count
        call_count += 1
        print(f"Hotkey pressed! Count: {call_count}")

    manager.set_toggle_record_callback(test_callback)

    print(f"Listening for {cfg.hotkey.toggle_record} key. Press it 3 times...")
    print("(This is a test mode - you can close with Ctrl+C)")

    try:
        while call_count < 3:
            keyboard.wait()
    except KeyboardInterrupt:
        print("Test ended")
    finally:
        manager.unregister_hotkeys()

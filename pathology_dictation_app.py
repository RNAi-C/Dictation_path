"""
Pathology Dictation Assistant - Main Application
Local, offline speech-to-text with terminology correction for pathology reports.

Phase 1: Push-to-talk with hotkey recording, local transcription, and terminology correction.
"""

import sys
from pathlib import Path
from typing import Optional
from loguru import logger

from config import PathologyDictationConfig
from audio_recorder import AudioRecorder
from transcriber import PathologyTranscriber
from terminology_corrector import TerminologyCorrector
from clipboard_handler import ClipboardHandler
from hotkey_manager import HotkeyManager


class PathologyDictationApp:
    """Main application controller."""

    def __init__(self, config: Optional[PathologyDictationConfig] = None):
        """
        Initialize the Pathology Dictation Assistant.

        Args:
            config: optional custom configuration
        """
        self.config = config or PathologyDictationConfig()

        # Initialize components
        self._setup_logging()

        logger.info("=" * 70)
        logger.info("Pathology Dictation Assistant - Phase 1")
        logger.info("=" * 70)

        self.audio_recorder = AudioRecorder(self.config.audio, self.config.audio_dir)
        self.transcriber = PathologyTranscriber(self.config.transcription, self.config.models_dir)
        self.terminology_corrector = TerminologyCorrector(
            self.config.dictionary,
            self.config.dictionary_path
        )
        self.clipboard_handler = ClipboardHandler()
        self.hotkey_manager = HotkeyManager(self.config.hotkey)

        # Set hotkey callback
        self.hotkey_manager.set_toggle_record_callback(self._on_toggle_record)

        # State
        self.is_recording = False
        self.last_transcription = None

        logger.info("Application initialized successfully")

    def _setup_logging(self) -> None:
        """Configure logging with loguru."""
        # Remove default handler
        logger.remove()

        # Add console handler with formatting
        log_format = "<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        logger.add(
            sys.stderr,
            format=log_format,
            level="INFO"
        )

        # Add file handler
        log_file = self.config.data_dir / "pathology_dictation.log"
        logger.add(
            str(log_file),
            format=log_format,
            level="DEBUG",
            rotation="10 MB",
            retention="7 days"
        )

        logger.info(f"Logging configured. Log file: {log_file}")

    def _on_toggle_record(self) -> None:
        """Hotkey callback for recording toggle."""
        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_and_transcribe()

    def _start_recording(self) -> None:
        """Start audio recording."""
        logger.info("Recording started (press F9 again to stop)")
        self.is_recording = True

        try:
            self.audio_recorder.start_recording()
            if self.config.ui.show_console_output:
                print("\n🎤 Recording... (Press F9 to stop)")

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.is_recording = False
            if self.config.ui.show_console_output:
                print(f"❌ Recording failed: {e}")

    def _stop_and_transcribe(self) -> None:
        """Stop recording and process the audio."""
        logger.info("Stopping recording...")
        self.is_recording = False

        try:
            # Stop recording and get audio
            audio_data = self.audio_recorder.stop_recording()

            if audio_data is None or len(audio_data) == 0:
                if self.config.ui.show_console_output:
                    print("❌ No audio recorded")
                logger.warning("No audio data captured")
                return

            if self.config.ui.show_console_output:
                print("\n📝 Transcribing...")

            # Transcribe
            raw_text = self.transcriber.transcribe(audio_data, self.config.audio.sample_rate)

            if not raw_text:
                if self.config.ui.show_console_output:
                    print("❌ Transcription produced no text")
                logger.warning("Transcription returned empty text")
                return

            # Apply terminology corrections
            if self.config.ui.show_console_output:
                print("🔧 Applying terminology corrections...")

            corrected_text, replacements = self.terminology_corrector.correct_with_logging(raw_text)

            # Save to clipboard
            if self.config.ui.auto_copy_to_clipboard:
                success = self.clipboard_handler.copy_to_clipboard(corrected_text)
                if success and self.config.ui.show_console_output:
                    print("✅ Copied to clipboard!")
                elif not success and self.config.ui.show_console_output:
                    print("⚠️  Failed to copy to clipboard")

            # Store for reference
            self.last_transcription = {
                'raw': raw_text,
                'corrected': corrected_text,
                'replacements': replacements
            }

            # Display results
            if self.config.ui.show_console_output:
                print("\n" + "=" * 70)
                print("TRANSCRIPTION RESULT")
                print("=" * 70)
                print(f"\nOriginal: {raw_text}\n")
                print(f"Corrected: {corrected_text}")
                print("\n" + "=" * 70)
                if replacements:
                    print("Corrections applied:")
                    for r in replacements:
                        print(f"  • '{r['original']}' → '{r['replacement']}' ({r['count']}x)")
                print("=" * 70 + "\n")

        except Exception as e:
            logger.error(f"Error during transcription: {e}", exc_info=True)
            if self.config.ui.show_console_output:
                print(f"❌ Error: {e}")

    def test_microphone(self) -> bool:
        """Test microphone connectivity."""
        logger.info("Testing microphone...")
        success = self.audio_recorder.test_microphone(duration_seconds=2)

        if success:
            logger.info("✅ Microphone test successful")
            if self.config.ui.show_console_output:
                print("✅ Microphone is working correctly")
        else:
            logger.error("❌ Microphone test failed")
            if self.config.ui.show_console_output:
                print("❌ Microphone test failed - check your audio device")

        return success

    def print_info(self) -> None:
        """Print application info and status."""
        print("\n" + "=" * 70)
        print("PATHOLOGY DICTATION ASSISTANT - Phase 1")
        print("=" * 70)
        print(f"Status: {'Recording' if self.is_recording else 'Idle'}")
        print(f"Hotkey: {self.config.hotkey.toggle_record.upper()}")
        print(f"Model: {self.config.transcription.model_size}")
        print(f"Device: {self.config.transcription.device}")
        print(f"Dictionary: {self.config.dictionary_path.name}")
        print(f"Auto-clipboard: {self.config.ui.auto_copy_to_clipboard}")
        print("=" * 70)
        print("\nWorkflow:")
        print("  1. Press F9 to start recording")
        print("  2. Speak your pathology dictation")
        print("  3. Press F9 again to stop and transcribe")
        print("  4. Text is automatically copied to clipboard")
        print("  5. Paste into LIS, Word, or your report system")
        print("\n" + "=" * 70 + "\n")

    def run(self) -> None:
        """Run the application (blocking)."""
        try:
            self.print_info()

            # Test microphone first
            if not self.test_microphone():
                logger.error("Microphone test failed. Exiting.")
                print("\n⚠️  Please check your microphone and try again.")
                return

            # Display ready message
            print("\n🚀 Ready! Press F9 to start recording...")
            print("Press Ctrl+C to exit.\n")

            # Keep running
            import time
            while True:
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\n\n👋 Shutting down...")
            logger.info("Application shutdown requested")
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            print(f"\n❌ Unexpected error: {e}")
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up resources...")

        try:
            if self.is_recording:
                self.audio_recorder.stop_recording()

            self.hotkey_manager.unregister_hotkeys()

            logger.info("Cleanup complete. Goodbye!")
            print("✅ Cleanup complete. Goodbye!\n")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


def main():
    """Entry point."""
    try:
        app = PathologyDictationApp()
        app.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Audio recording module for Pathology Dictation Assistant.
Handles microphone input and audio buffering using sounddevice.
"""

import sounddevice as sd
import soundfile as sf
import numpy as np
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
from loguru import logger
import threading
import queue

from config import AudioConfig


class AudioRecorder:
    """Handles audio recording and buffering."""

    def __init__(self, config: AudioConfig, audio_dir: Path):
        self.config = config
        self.audio_dir = audio_dir
        self.audio_dir.mkdir(exist_ok=True)

        self.is_recording = False
        self.audio_buffer = []
        self.stream = None
        self.audio_queue = queue.Queue()

        logger.info(
            f"AudioRecorder initialized: {config.sample_rate}Hz, "
            f"{config.channels} channel, device={config.device_index}"
        )

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """Callback for audio stream. Called by sounddevice in separate thread."""
        if status:
            logger.warning(f"Audio stream status: {status}")

        # Copy audio data to buffer
        self.audio_buffer.append(indata.copy())

    def start_recording(self) -> None:
        """Start recording audio from microphone."""
        if self.is_recording:
            logger.warning("Already recording. Ignoring start_recording request.")
            return

        self.audio_buffer = []
        self.is_recording = True

        try:
            self.stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                blocksize=self.config.chunk_size,
                device=self.config.device_index,
                dtype=self.config.dtype,
                callback=self._audio_callback
            )
            self.stream.start()
            logger.info("Recording started")

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.is_recording = False
            raise

    def stop_recording(self) -> np.ndarray:
        """Stop recording and return audio data as numpy array."""
        if not self.is_recording:
            logger.warning("Not currently recording.")
            return None

        self.is_recording = False

        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None

            if not self.audio_buffer:
                logger.warning("No audio data recorded.")
                return None

            # Concatenate all audio chunks into single array
            audio_data = np.concatenate(self.audio_buffer, axis=0)
            logger.info(f"Recording stopped. Captured {len(audio_data)} samples "
                       f"({len(audio_data) / self.config.sample_rate:.2f} seconds)")

            return audio_data

        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            raise

    def save_audio(self, audio_data: np.ndarray, filename: Optional[str] = None) -> Path:
        """
        Save recorded audio to WAV file.

        Args:
            audio_data: numpy array of audio samples
            filename: optional custom filename. If None, uses timestamp.

        Returns:
            Path to saved audio file
        """
        if audio_data is None or len(audio_data) == 0:
            logger.warning("No audio data to save.")
            return None

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{timestamp}.wav"

        filepath = self.audio_dir / filename

        try:
            sf.write(str(filepath), audio_data, self.config.sample_rate)
            logger.info(f"Audio saved to {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Failed to save audio: {e}")
            raise

    def get_device_info(self) -> dict:
        """Get information about available audio devices."""
        devices = sd.query_devices()
        return {
            'default_device': sd.default.device,
            'devices': devices
        }

    def test_microphone(self, duration_seconds: float = 2.0) -> bool:
        """
        Test microphone with short recording.

        Args:
            duration_seconds: length of test recording

        Returns:
            True if test successful, False otherwise
        """
        try:
            logger.info(f"Testing microphone for {duration_seconds}s...")
            audio_data = sd.rec(
                int(self.config.sample_rate * duration_seconds),
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                device=self.config.device_index,
                dtype=self.config.dtype
            )
            sd.wait()

            # Check if we got audio data
            if audio_data is not None and len(audio_data) > 0:
                logger.info("Microphone test successful")
                return True
            else:
                logger.error("Microphone test failed: no audio captured")
                return False

        except Exception as e:
            logger.error(f"Microphone test failed: {e}")
            return False


if __name__ == "__main__":
    # Simple test
    from config import PathologyDictationConfig

    cfg = PathologyDictationConfig()
    recorder = AudioRecorder(cfg.audio, cfg.audio_dir)

    # Test microphone
    if recorder.test_microphone(duration_seconds=2):
        print("Microphone is working!")
    else:
        print("Microphone test failed.")

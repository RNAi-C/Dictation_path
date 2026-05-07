"""
Transcription module for Pathology Dictation Assistant.
Uses faster-whisper for fast, local speech-to-text.
"""

import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple
from loguru import logger

from faster_whisper import WhisperModel
from config import TranscriptionConfig


class PathologyTranscriber:
    """Handles speech-to-text transcription using faster-whisper."""

    def __init__(self, config: TranscriptionConfig, models_dir: Path):
        self.config = config
        self.models_dir = models_dir
        self.models_dir.mkdir(exist_ok=True)

        self.model = None
        self._load_model()

        logger.info(
            f"PathologyTranscriber initialized: model={config.model_size}, "
            f"device={config.device}, compute_type={config.compute_type}"
        )

    def _load_model(self) -> None:
        """Load the Whisper model. Downloads if not cached."""
        import os
        try:
            model_path = self.config.model_size
            device     = self.config.device
            compute    = self.config.compute_type

            # auto device: try CUDA, fall back to CPU
            if device == "auto":
                try:
                    import ctranslate2
                    if ctranslate2.get_cuda_device_count() > 0:
                        device  = "cuda"
                        compute = "float16"
                        logger.info("Auto-detected CUDA GPU — using float16")
                    else:
                        raise RuntimeError("no CUDA device")
                except Exception:
                    device  = "cpu"
                    compute = "int8"
                    logger.info("No CUDA GPU detected — using CPU int8")

            # In portable/offline mode never attempt a network download
            offline = os.environ.get("PATHDICTATE_PORTABLE") == "1" \
                   or os.environ.get("HF_HUB_OFFLINE") == "1"

            logger.info(f"Loading Whisper model: {model_path}  device={device}  "
                        f"compute={compute}  offline={offline}")

            self.model = WhisperModel(
                model_size_or_path=model_path,
                device=device,
                compute_type=compute,
                download_root=str(self.models_dir),
                local_files_only=offline,
            )

            logger.info(f"Model loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise

    def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> str:
        """
        Transcribe audio data to text.

        Args:
            audio_data: numpy array of audio samples
            sample_rate: sample rate of audio (default 16000)

        Returns:
            Transcribed text
        """
        if audio_data is None or len(audio_data) == 0:
            logger.warning("No audio data to transcribe")
            return ""

        try:
            logger.info("Starting transcription...")

            # Flatten if stereo, ensure float32
            if len(audio_data.shape) > 1:
                audio_data = audio_data.squeeze()

            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            # Normalize audio
            max_val = np.abs(audio_data).max()
            if max_val > 0:
                audio_data = audio_data / max_val

            # Transcribe
            segments, info = self.model.transcribe(
                audio=audio_data,
                language=self.config.language,
                temperature=self.config.temperature,
                beam_size=self.config.beam_size,
                best_of=self.config.best_of,
                word_timestamps=False,
                vad_filter=True  # Use VAD to filter silence
            )

            # Combine segments into single text
            full_text = ""
            for segment in segments:
                full_text += segment.text + " "

            full_text = full_text.strip()

            logger.info(f"Transcription complete. Text length: {len(full_text)} characters")
            logger.debug(f"Transcribed text: {full_text[:100]}...")

            return full_text

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise

    def transcribe_from_file(self, audio_path: Path) -> str:
        """
        Transcribe audio from a file.

        Args:
            audio_path: Path to audio file

        Returns:
            Transcribed text
        """
        try:
            import soundfile as sf

            logger.info(f"Loading audio file: {audio_path}")
            audio_data, sample_rate = sf.read(str(audio_path))

            return self.transcribe(audio_data, sample_rate)

        except Exception as e:
            logger.error(f"Failed to transcribe file {audio_path}: {e}")
            raise

    def get_model_info(self) -> dict:
        """Get information about loaded model."""
        return {
            'model_size': self.config.model_size,
            'device': self.config.device,
            'compute_type': self.config.compute_type,
            'language': self.config.language
        }


if __name__ == "__main__":
    # Simple test
    from config import PathologyDictationConfig

    cfg = PathologyDictationConfig()
    transcriber = PathologyTranscriber(cfg.transcription, cfg.models_dir)

    print(f"Model info: {transcriber.get_model_info()}")

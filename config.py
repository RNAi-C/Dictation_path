"""
Configuration module for Pathology Dictation Assistant.
Handles settings, paths, and model configuration.
"""

import os
from pathlib import Path
from typing import Optional
import json
from dataclasses import dataclass, asdict


@dataclass
class AudioConfig:
    """Audio recording configuration."""
    sample_rate: int = 16000  # Whisper expects 16kHz
    channels: int = 1  # Mono
    chunk_size: int = 1024  # Buffer size
    device_index: Optional[int] = None  # Default system microphone
    dtype: str = "float32"


@dataclass
class TranscriptionConfig:
    """Faster-Whisper transcription configuration."""
    model_size: str = "large-v3"  # Options: tiny, base, small, medium, large, large-v3
    device: str = "cuda"          # Options: auto, cuda, cpu
    compute_type: str = "float16" # Options: float32, float16, int8
    language: str = "en"          # ISO 639-1 code
    temperature: float = 0.0
    beam_size: int = 5
    best_of: int = 5


@dataclass
class DictionaryConfig:
    """Terminology correction dictionary configuration."""
    enabled: bool = True
    case_sensitive: bool = False
    dictionary_file: str = "pathology_dictionary.json"


@dataclass
class HotkeyConfig:
    """Hotkey configuration."""
    toggle_record: str = "f9"  # Press once to start, once to stop


@dataclass
class UIConfig:
    """UI and UX configuration."""
    show_transcription_live: bool = True
    auto_copy_to_clipboard: bool = True
    show_console_output: bool = True


@dataclass
class LLMConfig:
    """Local LLM rewrite configuration (Ollama)."""
    enabled:                      bool  = True
    provider:                     str   = "ollama"
    endpoint:                     str   = "http://localhost:11434"
    model:                        str   = "qwen2.5:14b"
    temperature:                  float = 0.1
    max_tokens:                   int   = 512
    timeout_seconds:              int   = 120
    # Auto-start settings
    auto_start_ollama:            bool  = True
    ollama_start_command:         str   = "ollama serve"
    startup_wait_seconds:         int   = 30
    startup_retry_interval_seconds: int = 2


class PathologyDictationConfig:
    """Main configuration manager."""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path(__file__).parent / "config"
        self.config_dir.mkdir(exist_ok=True)

        self.audio = AudioConfig()
        self.transcription = TranscriptionConfig()
        self.dictionary = DictionaryConfig()
        self.hotkey = HotkeyConfig()
        self.ui = UIConfig()
        self.llm = LLMConfig()

        # Paths
        self.project_root = Path(__file__).parent
        self.models_dir = self.project_root / "models"
        self.audio_dir = self.project_root / "audio"
        self.data_dir = self.project_root / "data"

        # Dictionary file path
        self.dictionary_path = self.data_dir / self.dictionary.dictionary_file

        # ── Portable / offline mode ───────────────────────────────────────────
        # When launched via start_app.bat, PATHDICTATE_PORTABLE=1 and
        # PATHDICTATE_ROOT=<portable folder> are set.  Override defaults so the
        # app works on CPU-only machines without downloading anything.
        portable_root_env = os.environ.get("PATHDICTATE_ROOT", "")
        if os.environ.get("PATHDICTATE_PORTABLE") == "1" and portable_root_env:
            portable_root = Path(portable_root_env)
            self.project_root = portable_root
            self.models_dir   = portable_root / "models"
            self.audio_dir    = portable_root / "audio"
            self.data_dir     = portable_root / "data"

            # Load config.yaml if present
            yaml_cfg = portable_root / "config" / "config.yaml"
            if yaml_cfg.exists():
                self._apply_yaml(yaml_cfg, portable_root)
            else:
                # Safe CPU-first defaults
                self.transcription.device        = "auto"
                self.transcription.compute_type  = "int8"
                self.transcription.model_size    = str(self.models_dir / "faster-whisper-base")

            # Point dictionary at portable config folder
            dict_portable = portable_root / "config" / "pathology_replacements.json"
            if dict_portable.exists():
                self.dictionary_path = dict_portable

        self.models_dir.mkdir(exist_ok=True)
        self.audio_dir.mkdir(exist_ok=True)
        self.data_dir.mkdir(exist_ok=True)

        # Always load LLM (and privacy) config from config.yaml when present —
        # works in both dev and portable mode.
        yaml_path = self.config_dir / "config.yaml"
        if yaml_path.exists():
            self._load_llm_from_yaml(yaml_path)

    def _load_llm_from_yaml(self, yaml_path: Path) -> None:
        """Parse the 'llm:' block from config.yaml and update self.llm."""
        try:
            import yaml
            import urllib.parse as _up
            with open(yaml_path, encoding="utf-8") as f:
                y = yaml.safe_load(f) or {}
            llm = y.get("llm", {})
            if not llm:
                return

            self.llm.enabled  = bool(llm.get("enabled",  self.llm.enabled))
            self.llm.provider = str( llm.get("provider", self.llm.provider))

            # endpoint: accept full URL (with path) or just base — normalise to
            # scheme+host so OllamaClient can derive /api/generate and /api/tags.
            ep     = str(llm.get("endpoint", self.llm.endpoint))
            parsed = _up.urlparse(ep)
            if parsed.netloc:
                self.llm.endpoint = f"{parsed.scheme}://{parsed.netloc}"
            elif ":" in ep:          # bare  host:port  without scheme
                self.llm.endpoint = f"http://{ep}"
            else:
                self.llm.endpoint = ep

            self.llm.model           = str(  llm.get("model",           self.llm.model))
            self.llm.temperature     = float(llm.get("temperature",     self.llm.temperature))
            self.llm.max_tokens      = int(  llm.get("max_tokens",      self.llm.max_tokens))
            self.llm.timeout_seconds = int(  llm.get("timeout_seconds", self.llm.timeout_seconds))

            # Auto-start settings
            self.llm.auto_start_ollama  = bool(llm.get(
                "auto_start_ollama",  self.llm.auto_start_ollama))
            self.llm.ollama_start_command = str(llm.get(
                "ollama_start_command", self.llm.ollama_start_command))
            self.llm.startup_wait_seconds = int(llm.get(
                "startup_wait_seconds", self.llm.startup_wait_seconds))
            self.llm.startup_retry_interval_seconds = int(llm.get(
                "startup_retry_interval_seconds",
                self.llm.startup_retry_interval_seconds))

        except Exception as exc:
            print(f"[config] Warning: could not load LLM config: {exc}")

    def _apply_yaml(self, yaml_path: Path, portable_root: Path) -> None:
        """Apply config.yaml overrides (portable mode only)."""
        try:
            import yaml
            with open(yaml_path, encoding="utf-8") as f:
                y = yaml.safe_load(f) or {}

            def resolve(p: str) -> str:
                """Resolve ./relative paths against portable_root."""
                if p.startswith("./") or p.startswith(".\\"):
                    return str(portable_root / p[2:])
                return p

            mp = y.get("model_path", "")
            if mp:
                self.transcription.model_size = resolve(mp)

            device = y.get("device", "auto")
            self.transcription.device = device

            # Pick compute type based on device preference
            import ctranslate2
            cuda_ok = False
            if device in ("auto", "cuda"):
                try:
                    cuda_ok = ctranslate2.get_cuda_device_count() > 0
                except Exception:
                    cuda_ok = False

            if cuda_ok:
                self.transcription.compute_type = y.get("cuda_compute_type", "float16")
                self.transcription.device = "cuda"
            else:
                self.transcription.compute_type = y.get("cpu_compute_type", "int8")
                self.transcription.device = "cpu"

            self.transcription.language    = y.get("language", "en")
            self.transcription.temperature = float(y.get("temperature", 0.0))
            self.transcription.beam_size   = int(y.get("beam_size", 5))
            self.transcription.best_of     = int(y.get("best_of", 5))

            self.hotkey.toggle_record = y.get("hotkey_toggle_record", "f9")

            dict_file = y.get("dictionary_file", "")
            if dict_file:
                p = Path(resolve(dict_file))
                if p.exists():
                    self.dictionary_path = p

        except Exception as exc:
            print(f"[config] Warning: could not apply config.yaml: {exc}")

    def load_from_file(self, config_path: Path) -> None:
        """Load configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)

            # Update audio config
            if 'audio' in config_data:
                self.audio = AudioConfig(**config_data['audio'])

            # Update transcription config
            if 'transcription' in config_data:
                self.transcription = TranscriptionConfig(**config_data['transcription'])

            # Update other configs
            if 'dictionary' in config_data:
                self.dictionary = DictionaryConfig(**config_data['dictionary'])
            if 'hotkey' in config_data:
                self.hotkey = HotkeyConfig(**config_data['hotkey'])
            if 'ui' in config_data:
                self.ui = UIConfig(**config_data['ui'])

        except Exception as e:
            print(f"Warning: Could not load config file {config_path}: {e}")
            print("Using default configuration.")

    def save_to_file(self, config_path: Path) -> None:
        """Save configuration to JSON file."""
        config_data = {
            'audio': asdict(self.audio),
            'transcription': asdict(self.transcription),
            'dictionary': asdict(self.dictionary),
            'hotkey': asdict(self.hotkey),
            'ui': asdict(self.ui),
        }

        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)

        print(f"Configuration saved to {config_path}")


# Global config instance
config = PathologyDictationConfig()

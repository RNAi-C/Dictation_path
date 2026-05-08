"""
rewriter.py — Local LLM rewriting for Pathology Dictation Assistant
Uses llama-cpp-python to run GGUF models fully offline.

SAFETY RULE (enforced in system prompt):
    "Rewrite into my reporting style using only dictated facts."
    The model must NEVER add diagnoses, findings, or clinical content
    not present in the original dictation.

Supported models (place .gguf files in  models/rewrite/):
    Qwen2.5-1.5B-Instruct-Q4_K_M.gguf   ~0.9 GB  fastest CPU
    Qwen2.5-3B-Instruct-Q4_K_M.gguf     ~1.8 GB  good CPU balance
    Qwen2.5-7B-Instruct-Q4_K_M.gguf     ~4.4 GB  best Qwen, GPU recommended
    Phi-3.5-mini-instruct-Q4_K_M.gguf   ~2.2 GB  excellent for medical text
    Llama-3.2-1B-Instruct-Q4_K_M.gguf   ~0.7 GB  smallest / fastest

Download from HuggingFace (requires internet once on the build machine):
    https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF
    https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF
    https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF
"""

from pathlib import Path
from typing import Optional
from loguru import logger

# ── Safety-enforcing system prompt ────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "You are a pathology report formatter.\n"
    "Your only task is to rewrite dictated pathology text into clean, "
    "professional report language.\n\n"
    "STRICT RULES — you must follow ALL of these:\n"
    "1. Use ONLY facts explicitly stated in the dictation.\n"
    "2. Do NOT add any diagnosis, finding, or clinical information "
    "not present in the original text.\n"
    "3. Do NOT infer, speculate, or extend any finding.\n"
    "4. Fix grammar, punctuation, sentence structure, and formatting only.\n"
    "5. Preserve all medical terminology exactly as dictated.\n"
    "6. Keep the meaning and content identical to the dictation.\n"
    "7. Output only the reformatted text — no commentary, no explanations."
)

_USER_TEMPLATE = (
    "Rewrite the following dictated pathology text into clean report style.\n"
    "Use ONLY the stated facts. Do not add anything new.\n\n"
    "Dictated text:\n{text}\n\n"
    "Clean report:"
)


def scan_models(models_dir: Path) -> list[Path]:
    """Return all .gguf files found in models/rewrite/."""
    rewrite_dir = models_dir / "rewrite"
    rewrite_dir.mkdir(exist_ok=True)
    return sorted(rewrite_dir.glob("*.gguf"))


class LocalRewriter:
    """
    Wraps a llama-cpp-python Llama instance.
    Lazy-loaded: the model file is read only when rewrite() is first called.
    """

    def __init__(self, model_path: Path, n_ctx: int = 2048):
        self.model_path = model_path
        self.n_ctx      = n_ctx
        self._llm       = None

    # ── loading ───────────────────────────────────────────────────────────────

    @staticmethod
    def check_available() -> tuple[bool, str]:
        """Return (available, message). Checks llama_cpp import."""
        try:
            import llama_cpp          # noqa: F401
            return True, "llama-cpp-python is installed"
        except ImportError:
            return False, (
                "llama-cpp-python is not installed.\n\n"
                "Install with:\n"
                "  venv\\Scripts\\pip install llama-cpp-python\n\n"
                "For GPU acceleration (optional):\n"
                "  venv\\Scripts\\pip install llama-cpp-python "
                "--extra-index-url "
                "https://abetlen.github.io/llama-cpp-python/whl/cu121"
            )

    def load(self) -> None:
        """Load the model into memory (blocking — run in a thread)."""
        avail, msg = self.check_available()
        if not avail:
            raise RuntimeError(msg)
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model file not found:\n{self.model_path}\n\n"
                "Place a .gguf file in  models/rewrite/  to use this feature."
            )
        try:
            from llama_cpp import Llama
            logger.info(f"Loading rewrite model: {self.model_path.name}")
            # n_gpu_layers=-1 uses all GPU layers when CUDA is available;
            # falls back to CPU automatically when no GPU is present.
            self._llm = Llama(
                model_path   = str(self.model_path),
                n_ctx        = self.n_ctx,
                n_gpu_layers = -1,
                verbose      = False,
            )
            logger.info(f"Rewrite model loaded: {self.model_path.name}")
        except Exception as exc:
            self._llm = None
            raise RuntimeError(
                f"Failed to load {self.model_path.name}:\n{exc}"
            ) from exc

    def is_loaded(self) -> bool:
        return self._llm is not None

    def unload(self) -> None:
        if self._llm:
            del self._llm
            self._llm = None
        logger.info("Rewrite model unloaded")

    # ── rewriting ─────────────────────────────────────────────────────────────

    def rewrite(self, text: str,
                max_tokens: int = 1024,
                temperature: float = 0.15) -> str:
        """
        Rewrite dictated text into clean pathology report style.

        SAFETY: Uses a system prompt that strictly forbids adding
        any findings not present in the original dictation.

        Args:
            text:        The corrected dictation text to reformat.
            max_tokens:  Maximum output tokens (default 1024).
            temperature: Lower = more deterministic (default 0.15).

        Returns:
            Reformatted text string.
        """
        if not self._llm:
            raise RuntimeError("Model is not loaded. Call load() first.")
        if not text.strip():
            return text

        prompt = _USER_TEMPLATE.format(text=text.strip())

        response = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            max_tokens  = max_tokens,
            temperature = temperature,
            stop        = ["</s>", "[INST]", "Dictated text:", "\n\nDictated"],
        )

        result = response["choices"][0]["message"]["content"].strip()
        logger.info(
            f"Rewrite done: {len(text)} chars in, {len(result)} chars out, "
            f"model={self.model_path.name}"
        )
        return result

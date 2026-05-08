"""
ollama_client.py — Local Ollama HTTP client for Pathology Dictation Assistant.

PRIVACY GUARANTEE:
  Connects ONLY to localhost (default: http://localhost:11434).
  No text is ever sent to an external server.
  No patient data is logged.

Usage:
  client = OllamaClient(endpoint="http://localhost:11434", model="qwen2.5:14b")
  text   = client.generate(system_prompt="...", user_text="...")
"""

import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional


# ── Exceptions ────────────────────────────────────────────────────────────────

class OllamaError(Exception):
    """Base class for all Ollama client errors."""


class OllamaConnectionError(OllamaError):
    """Raised when Ollama is not reachable (not running / wrong port)."""


class OllamaModelError(OllamaError):
    """Raised when the requested model is not available."""


# ── Client ────────────────────────────────────────────────────────────────────

class OllamaClient:
    """
    Thin wrapper around Ollama's /api/generate endpoint.
    Uses only Python stdlib (urllib) — no external dependencies.
    """

    def __init__(self,
                 endpoint: str = "http://localhost:11434",
                 model:    str = "qwen2.5:14b",
                 timeout:  int = 60):
        # Normalise: strip any path so we always work from the base URL.
        parsed = urllib.parse.urlparse(endpoint)
        self.base_url    = f"{parsed.scheme}://{parsed.netloc}"
        self.model       = model
        self.timeout     = timeout
        self._gen_url    = f"{self.base_url}/api/generate"
        self._tags_url   = f"{self.base_url}/api/tags"

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(self,
                 system_prompt: str,
                 user_text:     str,
                 temperature:   float = 0.1,
                 max_tokens:    int   = 512) -> str:
        """
        Call /api/generate (non-streaming) and return the response string.

        Args:
            system_prompt: System instruction sent to the model.
            user_text:     The text the model should process.
            temperature:   Sampling temperature (low = deterministic).
            max_tokens:    Maximum response tokens.

        Returns:
            The model's response as a stripped string.

        Raises:
            OllamaConnectionError: Ollama is not running.
            OllamaModelError:      The model has not been pulled.
            OllamaError:           Any other failure.
        """
        payload = {
            "model":   self.model,
            "system":  system_prompt,
            "prompt":  user_text,
            "stream":  False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            self._gen_url,
            data    = data,
            headers = {"Content-Type": "application/json"},
            method  = "POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body   = resp.read().decode("utf-8")
                result = json.loads(body)
                return result.get("response", "").strip()

        except urllib.error.URLError as exc:
            reason = str(exc.reason) if hasattr(exc, "reason") else str(exc)
            if any(k in reason.lower() for k in ("connection refused",
                                                  "refused", "timed out",
                                                  "cannot connect")):
                raise OllamaConnectionError(
                    f"Cannot connect to Ollama at {self.base_url}.\n\n"
                    "Make sure Ollama is running:\n"
                    "  1. Download from https://ollama.ai\n"
                    "  2. Open a terminal and run:  ollama serve\n"
                    f"\nExpected at: {self.base_url}"
                ) from exc
            raise OllamaError(f"Ollama request failed: {exc}") from exc

        except json.JSONDecodeError as exc:
            raise OllamaError(f"Unexpected response from Ollama: {exc}") from exc

        except Exception as exc:
            raise OllamaError(f"Ollama error: {exc}") from exc

    def check_status(self) -> tuple[bool, str]:
        """
        Check whether Ollama is running and the configured model is available.

        Returns:
            (True,  "Ready: <model>")          on success
            (False, "<human-readable message>") on any failure
        """
        try:
            req = urllib.request.Request(self._tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                body   = json.loads(resp.read().decode("utf-8"))
                models = [m["name"] for m in body.get("models", [])]

            # Match e.g. "qwen2.5:14b" against "qwen2.5:14b" or "qwen2.5"
            base = self.model.split(":")[0].lower()
            matches = [m for m in models
                       if m.lower() == self.model.lower()
                       or m.lower().startswith(base + ":")]

            if matches:
                return True, f"Ready: {matches[0]}"

            avail = ", ".join(models) if models else "(none)"
            return False, (
                f"Model '{self.model}' is not installed in Ollama.\n\n"
                f"Pull it with:\n  ollama pull {self.model}\n\n"
                f"Models currently available: {avail}"
            )

        except urllib.error.URLError as exc:
            return False, (
                f"Cannot reach Ollama at {self.base_url}.\n\n"
                "To start Ollama:\n"
                "  ollama serve\n\n"
                f"Detail: {exc}"
            )
        except Exception as exc:
            return False, f"Ollama status check failed: {exc}"

"""
ollama_client.py — Local Ollama HTTP client for Pathology Dictation Assistant.

PRIVACY GUARANTEE:
  Connects ONLY to localhost (default: http://localhost:11434).
  No text is ever sent to an external server.
  No patient data is logged.

Auto-start behaviour:
  OllamaClient.start_ollama()  — launches  "ollama serve"  silently via
  subprocess.Popen (no console window on Windows).
  OllamaClient.wait_until_ready()  — polls the /api/tags endpoint until
  Ollama responds or the timeout expires.
"""

import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


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
    Thin wrapper around Ollama's REST API.
    Uses only Python stdlib (urllib + subprocess) — no extra dependencies.

    All network calls target localhost exclusively.
    """

    def __init__(self,
                 endpoint: str = "http://localhost:11434",
                 model:    str = "qwen2.5:14b",
                 timeout:  int = 60):
        # Normalise: accept base URL or full endpoint URL — keep only scheme+host.
        parsed = urllib.parse.urlparse(endpoint)
        if parsed.netloc:
            self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        else:
            # bare host:port string like "localhost:11434"
            self.base_url = f"http://{endpoint}"
        self.model      = model
        self.timeout    = timeout
        self._gen_url   = f"{self.base_url}/api/generate"
        self._tags_url  = f"{self.base_url}/api/tags"

    # ── Status checks ─────────────────────────────────────────────────────────

    def is_ollama_running(self) -> bool:
        """
        Return True if Ollama's /api/tags endpoint responds within 3 seconds.
        Never raises — always returns a bool.
        """
        try:
            req = urllib.request.Request(self._tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=3):
                return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """
        Return a list of model name strings currently installed in Ollama.
        Returns [] on any error (including Ollama not running).
        """
        try:
            req = urllib.request.Request(self._tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in body.get("models", [])]
        except Exception:
            return []

    def is_model_available(self, model_name: Optional[str] = None) -> bool:
        """
        Return True if *model_name* (default: self.model) is installed.
        Returns False on any error.
        """
        target = (model_name or self.model).lower()
        base   = target.split(":")[0]
        models = self.list_models()
        return any(
            m.lower() == target or m.lower().startswith(base + ":")
            for m in models
        )

    def check_status(self) -> tuple[bool, str]:
        """
        Check whether Ollama is running AND self.model is available.

        Returns:
            (True,  "Ready: <model>")           — all good
            (False, "<human-readable message>") — any problem
        """
        if not self.is_ollama_running():
            return False, (
                f"Cannot reach Ollama at {self.base_url}.\n\n"
                "To start Ollama:\n  ollama serve"
            )
        models = self.list_models()
        base   = self.model.split(":")[0].lower()
        match  = next(
            (m for m in models
             if m.lower() == self.model.lower()
             or m.lower().startswith(base + ":")),
            None
        )
        if match:
            return True, f"Ready: {match}"
        avail = ", ".join(models) if models else "(none)"
        return False, (
            f"Model '{self.model}' is not installed in Ollama.\n\n"
            f"Pull it with:\n  ollama pull {self.model}\n\n"
            f"Models currently available: {avail}"
        )

    # ── Auto-start ────────────────────────────────────────────────────────────

    def start_ollama(self,
                     command: str = "ollama serve") -> bool:
        """
        Attempt to start Ollama silently in the background.

        On Windows the process is started with CREATE_NO_WINDOW so no
        console window appears.  stdout/stderr are discarded.

        Returns True if the process was *launched* (not necessarily ready).
        Returns False if the executable was not found or launch failed.

        Caller should follow up with wait_until_ready() to confirm readiness.
        """
        args = command.split()
        try:
            _popen_silent(args)
            logger.info(f"Launched Ollama: {command}")
            return True
        except FileNotFoundError:
            logger.warning(f"'{args[0]}' not found in PATH — trying fallback locations")
            return self._start_ollama_fallback(args[1:])
        except Exception as exc:
            logger.warning(f"Could not start Ollama: {exc}")
            return False

    def _start_ollama_fallback(self, extra_args: list[str]) -> bool:
        """Try well-known Ollama install paths on Windows."""
        if sys.platform != "win32":
            return False
        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Ollama\ollama.exe"),
            r"C:\Program Files\Ollama\ollama.exe",
            r"C:\Ollama\ollama.exe",
        ]
        for exe in candidates:
            if os.path.exists(exe):
                try:
                    _popen_silent([exe, "serve"] + extra_args)
                    logger.info(f"Launched Ollama from: {exe}")
                    return True
                except Exception as exc:
                    logger.debug(f"Fallback launch failed for {exe}: {exc}")
        logger.warning("Ollama executable not found in any fallback location")
        return False

    def wait_until_ready(self,
                         timeout:  int   = 30,
                         interval: float = 2.0) -> bool:
        """
        Poll /api/tags until Ollama responds or timeout expires.

        Args:
            timeout:  Maximum seconds to wait.
            interval: Seconds between retry attempts.

        Returns:
            True  if Ollama became reachable within the timeout.
            False if it did not respond in time.
        """
        deadline = time.monotonic() + timeout
        attempt  = 0
        while time.monotonic() < deadline:
            attempt += 1
            if self.is_ollama_running():
                logger.info(f"Ollama ready after {attempt} poll(s)")
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))
        logger.warning(f"Ollama did not become ready within {timeout} s")
        return False

    # ── Text generation ───────────────────────────────────────────────────────

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
            if any(k in reason.lower() for k in (
                    "connection refused", "refused",
                    "timed out", "cannot connect")):
                raise OllamaConnectionError(
                    f"Cannot connect to Ollama at {self.base_url}.\n\n"
                    "Make sure Ollama is running:\n  ollama serve\n\n"
                    f"Expected at: {self.base_url}"
                ) from exc
            raise OllamaError(f"Ollama request failed: {exc}") from exc

        except json.JSONDecodeError as exc:
            raise OllamaError(
                f"Unexpected response from Ollama: {exc}") from exc

        except Exception as exc:
            raise OllamaError(f"Ollama error: {exc}") from exc


# ── Internal helpers ──────────────────────────────────────────────────────────

def _popen_silent(args: list[str]) -> subprocess.Popen:
    """
    Launch a process with stdout/stderr discarded.
    On Windows, CREATE_NO_WINDOW prevents a console window from appearing.
    """
    kwargs: dict = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(args, **kwargs)

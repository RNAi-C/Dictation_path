"""
rewrite_service.py — Pathology-safe text rewriting via Ollama.

SAFETY GUARANTEE:
  The system prompt strictly forbids the model from:
    • Adding diagnoses not present in the selected text
    • Inferring findings, staging, or biomarker status
    • Converting hedged language into definite statements
    • Creating synoptic reports

  The model is instructed to rewrite STYLE only, never CONTENT.

PRIVACY GUARANTEE:
  All calls go through OllamaClient which only connects to localhost.
  Selected text is never logged (log_llm_requests defaults to False).
"""

import re
from ollama_client import OllamaClient, OllamaError, OllamaConnectionError  # noqa: F401

# ── Safety system prompt ──────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a pathology report rewriting assistant.\n\n"
    "Rewrite the selected text into clearer formal pathology reporting style "
    "using only the facts explicitly present in the selected text.\n\n"
    "STRICT RULES — follow ALL of these:\n"
    "• Do not add new findings.\n"
    "• Do not infer diagnosis.\n"
    "• Do not infer tumor type, grade, size, margin status, "
    "lymphovascular invasion, biomarker status, stage, or treatment effect.\n"
    "• Do not remove uncertainty.\n"
    "• Do not convert suspicious / possible / probable into definite.\n"
    "• Do not create a synoptic report.\n"
    "• Preserve all medical terminology exactly as written.\n"
    "• Return only the rewritten text — no explanations, no preamble."
)

_USER_TEMPLATE = "Rewrite the following pathology text:\n\n{text}"

# Preamble phrases the model sometimes adds despite instructions
_PREAMBLE_RE = re.compile(
    r"^(here\s+is|here'?s|rewritten(\s+text)?:?|"
    r"sure[,.]?|certainly[,.]?|of course[,.]?|"
    r"below\s+is|the\s+rewritten)[^\n]*\n*",
    re.IGNORECASE | re.MULTILINE,
)


# ── Service ───────────────────────────────────────────────────────────────────

class RewriteService:
    """
    Wraps OllamaClient with the pathology-safe system prompt.
    One instance can be reused for multiple rewrites.
    """

    def __init__(self,
                 client:      OllamaClient,
                 temperature: float = 0.1,
                 max_tokens:  int   = 512):
        self.client      = client
        self.temperature = temperature
        self.max_tokens  = max_tokens

    def rewrite(self, selected_text: str) -> str:
        """
        Rewrite *selected_text* using the safety system prompt.

        Args:
            selected_text: The text selected by the user in the Corrected panel.

        Returns:
            Cleaned-up rewritten text (preamble stripped).

        Raises:
            OllamaConnectionError: Ollama is not running.
            OllamaModelError:      Model not pulled.
            OllamaError:           Any other failure.
            ValueError:            Empty input.
        """
        text = selected_text.strip()
        if not text:
            raise ValueError("Selected text is empty.")

        prompt = _USER_TEMPLATE.format(text=text)
        raw    = self.client.generate(
            system_prompt = _SYSTEM_PROMPT,
            user_text     = prompt,
            temperature   = self.temperature,
            max_tokens    = self.max_tokens,
        )
        return _clean_response(raw)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_response(text: str) -> str:
    """Strip common LLM preamble/suffix that leaks through despite instructions."""
    text = text.strip()
    # Remove leading preamble lines
    text = _PREAMBLE_RE.sub("", text).strip()
    # Remove trailing meta-comment (e.g. "Note: ..." on its own line)
    lines = text.splitlines()
    while lines and re.match(
            r"^(note:|note\s*—|this\s+rewrite|i\s+have)", lines[-1], re.I):
        lines.pop()
    return "\n".join(lines).strip()

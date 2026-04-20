"""
Translation Routing Logic
==========================
Selects the most cost-effective LLM provider for each task based on the
content complexity and the configured routing mode.

Routing strategy (default: "hybrid")
-------------------------------------
  analyze          → Ollama  (structured extraction; no premium model needed)
  translate simple → Ollama  (short paragraphs, plain language)
  translate complex→ Cerebras (medical codes, clinical criteria language)
  fallback         → Cerebras whenever Ollama is unavailable or returns empty

Routing modes (set via ROUTING_MODE in config or --provider CLI flag)
----------------------------------------------------------------------
  "hybrid"        — recommended default: Ollama for simple, Cerebras for complex
  "ollama-only"   — local model for all tasks; falls back to Cerebras on failure
  "cerebras-only" — Cerebras for everything (preserves original behaviour)
"""

import re
from typing import Tuple

import config
from llm_providers import CerebrasProvider, LLMProvider, OllamaProvider


# ─── Complexity Detection Patterns ───────────────────────────────────────────
# Patterns that indicate content requiring the premium Cerebras model.

_COMPLEX_PATTERNS = [
    re.compile(r"\b[A-Z]\d{2,3}\.?\d*\b"),           # ICD-10 codes: M54.5, J45.90
    re.compile(r"\b\d{4,5}[A-Z]?\b"),                # CPT numeric: 99213
    re.compile(r"\b[A-Z]\d{4}\b"),                   # HCPCS alpha: G0439
    re.compile(
        r"\b("
        r"prior authorization|clinical criteria|medically necessary|"
        r"level of care|formulary|utilization review|appeals process|"
        r"grievance|adverse determination|internal appeal"
        r")\b",
        re.IGNORECASE,
    ),
]


def _is_complex_content(text: str) -> bool:
    """Return True if text contains medical codes or complex clinical language."""
    return any(p.search(text) for p in _COMPLEX_PATTERNS)


# ─── Router ───────────────────────────────────────────────────────────────────

class TranslationRouter:
    """
    Routes each translation task to the most cost-effective LLM provider
    while maintaining output quality through automatic Cerebras fallback.

    Usage::

        router = TranslationRouter()          # reads mode from config.ROUTING_MODE
        router = TranslationRouter("hybrid")  # explicit mode

        result, provider_label = router.call_with_fallback(
            task_type="translate",
            system_prompt=sys_prompt,
            user_prompt=paragraph_text,
        )
    """

    def __init__(self, mode: str | None = None) -> None:
        self._mode = mode or config.ROUTING_MODE
        self._ollama = OllamaProvider()
        self._cerebras = CerebrasProvider()
        self._ollama_ok: bool | None = None  # lazily probed on first call

    # ── Public ────────────────────────────────────────────────────────────────

    def call_with_fallback(
        self,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
    ) -> Tuple[str, str]:
        """
        Call the selected provider; automatically fall back to Cerebras if
        Ollama is chosen but returns an empty response.

        Args:
            task_type    : ``"analyze"`` | ``"translate"``
            system_prompt: Instruction string.
            user_prompt  : Content string.

        Returns:
            ``(response_text, provider_label)`` — provider_label is a
            human-readable string describing which model actually responded.
        """
        provider = self._select(task_type, user_prompt)
        label = provider.name

        result = provider.call(system_prompt, user_prompt)

        # Fallback: Ollama was chosen but returned nothing → retry via Cerebras
        if not result and isinstance(provider, OllamaProvider):
            print("  [Router] Ollama returned empty — falling back to Cerebras.")
            result = self._cerebras.call(system_prompt, user_prompt)
            label = f"{self._cerebras.name}(fallback)"

        return result, label

    # ── Internal ──────────────────────────────────────────────────────────────

    def _ollama_available(self) -> bool:
        """Probe Ollama once and cache the result for the session lifetime."""
        if self._ollama_ok is None:
            if not config.OLLAMA_ENABLED:
                self._ollama_ok = False
            else:
                self._ollama_ok = self._ollama.is_available()
                if not self._ollama_ok:
                    print(
                        f"  [Router] Ollama not reachable at {config.OLLAMA_BASE_URL}"
                        " — all tasks will use Cerebras."
                    )
        return self._ollama_ok

    def _select(self, task_type: str, text: str) -> LLMProvider:
        """Choose the provider for a given task type and content."""
        # Hard overrides first
        if self._mode == "cerebras-only":
            return self._cerebras

        if self._mode == "ollama-only":
            return self._ollama if self._ollama_available() else self._cerebras

        # Hybrid routing
        if not self._ollama_available():
            return self._cerebras

        # Analysis: Ollama handles structured JSON extraction well
        if task_type == "analyze":
            return self._ollama

        # Complex medical/legal content → premium model
        if task_type == "translate" and _is_complex_content(text):
            return self._cerebras

        # Default: local model handles standard sentences
        return self._ollama

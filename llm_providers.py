"""
LLM Provider Abstraction Layer
===============================
Provides a unified interface for calling different LLM backends:

  - CerebrasProvider : Cerebras Cloud SDK  (premium model — complex tasks / fallback)
  - OllamaProvider   : Local Ollama HTTP API (open-source model — standard tasks)

Both providers implement the same ``LLMProvider`` interface so they are
interchangeable and the routing layer can swap between them transparently.
"""

import time
from abc import ABC, abstractmethod

import requests

import config


# ─── Abstract Base ────────────────────────────────────────────────────────────

class LLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    def call(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a system + user prompt pair and return the response text.
        Returns an empty string on unrecoverable failure (after all retries).
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider label used in log output."""
        ...


# ─── Cerebras Provider ────────────────────────────────────────────────────────

class CerebrasProvider(LLMProvider):
    """
    Cerebras Cloud SDK provider.
    Used for complex medical/legal content and as the automatic fallback when
    the local Ollama model is unavailable or returns an empty response.
    """

    def __init__(self) -> None:
        self._client = None  # lazy-initialised on first call

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_client(self):
        if self._client is None:
            from cerebras.cloud.sdk import Cerebras  # deferred import
            if not config.CEREBRAS_API_KEY:
                raise RuntimeError(
                    "CEREBRAS_API_KEY is not set. Add it to your .env file."
                )
            self._client = Cerebras(api_key=config.CEREBRAS_API_KEY)
        return self._client

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return f"Cerebras({config.CEREBRAS_MODEL})"

    def call(self, system_prompt: str, user_prompt: str) -> str:
        client = self._get_client()
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                stream = client.chat.completions.create(
                    model=config.CEREBRAS_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    stream=True,
                    max_completion_tokens=20_000,
                    temperature=0.1,
                    top_p=1,
                )
                result = ""
                for chunk in stream:
                    result += chunk.choices[0].delta.content or ""
                return result.strip()
            except Exception as exc:
                wait = config.RETRY_DELAY ** attempt
                print(
                    f"  [Cerebras retry {attempt}/{config.MAX_RETRIES}] "
                    f"{exc}. Waiting {wait}s..."
                )
                time.sleep(wait)
        print("  [Cerebras] All retries exhausted.")
        return ""


# ─── Ollama Provider ──────────────────────────────────────────────────────────

class OllamaProvider(LLMProvider):
    """
    Ollama local HTTP API provider.
    Used for document analysis and standard (non-complex) translation tasks.
    Communicates with the Ollama server running at ``OLLAMA_BASE_URL``.
    """

    def __init__(self) -> None:
        self._base_url = config.OLLAMA_BASE_URL.rstrip("/")
        self._model = config.OLLAMA_MODEL

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return f"Ollama({self._model})"

    def is_available(self) -> bool:
        """Probe the Ollama server. Returns True if the server is reachable."""
        try:
            resp = requests.get(f"{self._base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def call(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 1,
            },
        }
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                resp = requests.post(url, json=payload, timeout=config.OLLAMA_TIMEOUT)
                resp.raise_for_status()
                return resp.json()["message"]["content"].strip()
            except Exception as exc:
                wait = config.RETRY_DELAY ** attempt
                print(
                    f"  [Ollama retry {attempt}/{config.MAX_RETRIES}] "
                    f"{exc}. Waiting {wait}s..."
                )
                time.sleep(wait)
        print("  [Ollama] All retries exhausted.")
        return ""

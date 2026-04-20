"""
Configuration for AI Letter Translator.
All paths, model settings, and language mappings are centralized here.
"""
import os
from dotenv import load_dotenv
 
# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
 
# ─── Paths ───────────────────────────────────────────────────────────────────
SOURCE_FOLDER = (
    r"D:\Python Project\Input Letters"
)
OUTPUT_FOLDER = (
    r"D:\Python Project\Output Letters"
)
 
# ─── Cerebras API ────────────────────────────────────────────────────────────
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
CEREBRAS_MODEL = "qwen-3-235b-a22b-instruct-2507"
 
# ─── Translation settings ───────────────────────────────────────────────────
# Max retries for API calls
MAX_RETRIES = 3
# Delay between retries (seconds) — exponential backoff multiplier
RETRY_DELAY = 2

# ─── Ollama (local open-source LLM) ──────────────────────────────────────────
# Set OLLAMA_ENABLED=false in .env to force all traffic through Cerebras.
OLLAMA_ENABLED  = os.getenv("OLLAMA_ENABLED",  "true").lower() == "true"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL",    "gpt-oss:120b-cloud")
# Seconds to wait for a single Ollama response (large models can be slow)
OLLAMA_TIMEOUT  = int(os.getenv("OLLAMA_TIMEOUT", "120"))

# ─── Routing mode ─────────────────────────────────────────────────────────────
# "hybrid"        — Ollama for analysis + simple translations; Cerebras for complex
# "ollama-only"   — Ollama for every task (falls back to Cerebras on failure)
# "cerebras-only" — Cerebras for every task (original single-model behaviour)
ROUTING_MODE = os.getenv("ROUTING_MODE", "hybrid")

# ─── Paragraph batching ───────────────────────────────────────────────────────
# Paragraphs shorter than BATCH_THRESHOLD chars are grouped into batch API calls,
# avoiding the per-call system-prompt overhead for short content.
BATCH_THRESHOLD = int(os.getenv("BATCH_THRESHOLD", "200"))
# Maximum number of paragraphs sent in a single batch call.
BATCH_SIZE      = int(os.getenv("BATCH_SIZE", "5"))

# ─── Language code → language name mapping ───────────────────────────────────
LANGUAGE_MAP = {
    "es": "Spanish",
    "zh": "Chinese (Simplified)",
    "vi": "Vietnamese",
    "ko": "Korean",
    "ar": "Arabic",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ru": "Russian",
    "ja": "Japanese",
    "tl": "Tagalog",
    "hi": "Hindi",
    "km": "Khmer",
    "lo": "Lao",
    "my": "Burmese",
    "so": "Somali",
    "hmn": "Hmong",
    "en": "English",
    "te": "Telugu",
}
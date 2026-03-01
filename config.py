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
    r"C:\Users\theam\Downloads\medical-certificate-template-09"
)
OUTPUT_FOLDER = (
    r"d:\PROJECTS\AI TRANSLATOR\Translated Files"
)
 
# ─── Cerebras API ────────────────────────────────────────────────────────────
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
CEREBRAS_MODEL = "gpt-oss-120b"
 
# ─── Translation settings ───────────────────────────────────────────────────
# Max retries for API calls
MAX_RETRIES = 3
# Delay between retries (seconds) — exponential backoff multiplier
RETRY_DELAY = 2
 
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
}
"""
AI Letter Translator — Web UI
Flask application. Run with: python app.py

Calls the core translator via subprocess.
No imports from the core project — fully self-contained.
"""

import os
import sys
import subprocess
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# Configuration
# Update SOURCE_FOLDER / OUTPUT_FOLDER if the core project paths ever change.
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
CORE_SCRIPT = (BASE_DIR / ".." / "translator.py").resolve()

SOURCE_FOLDER = Path(r"D:\Python Project\Input Letters")
OUTPUT_FOLDER = Path(r"D:\Python Project\Output Letters")

MAX_FILE_MB = 50
TRANSLATION_TIMEOUT = 600  # seconds

# Hardcoded copy of config.LANGUAGE_MAP — keeps the UI independent of core code.
LANGUAGE_CODES = {
    "es":  "Spanish",
    "zh":  "Chinese (Simplified)",
    "vi":  "Vietnamese",
    "ko":  "Korean",
    "ar":  "Arabic",
    "fr":  "French",
    "de":  "German",
    "pt":  "Portuguese",
    "ru":  "Russian",
    "ja":  "Japanese",
    "tl":  "Tagalog",
    "hi":  "Hindi",
    "km":  "Khmer",
    "lo":  "Lao",
    "my":  "Burmese",
    "so":  "Somali",
    "hmn": "Hmong",
    "en":  "English",
    "te":  "Telugu",
}

PROVIDER_CHOICES = {
    "hybrid":      "Hybrid (Ollama + OpenAI)",
    "ollama-only": "Ollama Only",
    "openai-only": "OpenAI Only",
}

# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_MB * 1024 * 1024


@app.route("/")
def index():
    return render_template(
        "index.html",
        languages=LANGUAGE_CODES,
        providers=PROVIDER_CHOICES,
        max_mb=MAX_FILE_MB,
    )


@app.route("/translate", methods=["POST"])
def translate():
    # ── Validate uploaded file ──────────────────────────────────────────────
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify(success=False, error="No file was uploaded.")

    safe_name = secure_filename(uploaded.filename)
    if not safe_name.lower().endswith(".docx"):
        return jsonify(success=False, error="Only .docx files are supported.")

    # ── Validate form fields ────────────────────────────────────────────────
    lang_code = request.form.get("language", "").strip()
    provider  = request.form.get("provider", "hybrid").strip()

    if lang_code not in LANGUAGE_CODES:
        return jsonify(success=False, error="Invalid language selected.")
    if provider not in PROVIDER_CHOICES:
        return jsonify(success=False, error="Invalid provider selected.")

    # ── Build target filename: <stem>_<lang>.docx ───────────────────────────
    stem = Path(safe_name).stem
    # Strip any existing lang suffix to prevent doubling (e.g. letter_es_es.docx)
    for code in LANGUAGE_CODES:
        if stem.lower().endswith(f"_{code}"):
            stem = stem[: -(len(code) + 1)]
            break
    target_filename = f"{stem}_{lang_code}.docx"

    # ── Ensure folders exist ────────────────────────────────────────────────
    SOURCE_FOLDER.mkdir(parents=True, exist_ok=True)
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    source_path = SOURCE_FOLDER / target_filename
    uploaded.save(str(source_path))

    # ── Run the core translator as a subprocess ─────────────────────────────
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(CORE_SCRIPT),
                "--file", target_filename,
                "--provider", provider,
            ],
            capture_output=True,
            text=True,
            timeout=TRANSLATION_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        source_path.unlink(missing_ok=True)
        return jsonify(
            success=False,
            error="Translation timed out. The document may be too large.",
        )
    except Exception as exc:
        source_path.unlink(missing_ok=True)
        return jsonify(success=False, error=f"Failed to start translator: {exc}")

    # Clean up the source file now that translation has finished
    source_path.unlink(missing_ok=True)

    if result.returncode != 0:
        error_text = (result.stderr or result.stdout or "Unknown error").strip()
        return jsonify(success=False, error=error_text[-500:])

    output_path = OUTPUT_FOLDER / target_filename
    if not output_path.exists():
        return jsonify(
            success=False,
            error="Translation completed but the output file was not found.",
        )

    return jsonify(success=True, filename=target_filename)


@app.route("/download/<filename>")
def download(filename):
    safe_name = secure_filename(filename)
    output_path = (OUTPUT_FOLDER / safe_name).resolve()

    # Prevent path traversal attacks
    try:
        output_path.relative_to(OUTPUT_FOLDER.resolve())
    except ValueError:
        return "Forbidden", 403

    if not output_path.exists():
        return "File not found", 404

    return send_file(str(output_path), as_attachment=True, download_name=safe_name)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)

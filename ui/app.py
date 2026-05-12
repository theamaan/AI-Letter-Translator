"""
AI Letter Translator — Web UI
Flask application. Run with: python app.py

Calls the core translator via subprocess.
No imports from the core project — fully self-contained.
"""

import os
import sys
import subprocess
import json
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
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
    lang_code     = request.form.get("language", "").strip()
    provider      = request.form.get("provider", "hybrid").strip()
    spanish_grade = request.form.get("spanish_grade", "").strip()

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

    # ── Build command ───────────────────────────────────────────────────────
    cmd = [
        sys.executable,
        str(CORE_SCRIPT),
        "--file", target_filename,
        "--provider", provider,
    ]
    if lang_code == "es" and spanish_grade:
        cmd += ["--spanish-grade", spanish_grade]

    # ── Stream stdout line-by-line via Server-Sent Events ───────────────────
    def generate():
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for raw in proc.stdout:
                line = raw.rstrip()
                if line:
                    yield f"data: {json.dumps({'line': line})}\n\n"
            proc.wait()
        except Exception as exc:
            source_path.unlink(missing_ok=True)
            yield f"data: {json.dumps({'done': True, 'success': False, 'error': str(exc)})}\n\n"
            return

        source_path.unlink(missing_ok=True)

        if proc.returncode != 0:
            yield f"data: {json.dumps({'done': True, 'success': False, 'error': 'Translator exited with an error. See the log above for details.'})}\n\n"
            return

        output_path = OUTPUT_FOLDER / target_filename
        if not output_path.exists():
            yield f"data: {json.dumps({'done': True, 'success': False, 'error': 'Translation completed but the output file was not found.'})}\n\n"
            return

        yield f"data: {json.dumps({'done': True, 'success': True, 'filename': target_filename})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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

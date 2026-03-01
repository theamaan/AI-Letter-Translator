# AI Letter Translator

A small Python project that translates letter templates into multiple languages using an LLM API.

## Overview

This repository contains a set of scripts to translate letter templates (images and text) into other languages, plus helper inspection and verification tools. The core translator is `translator.py` and configuration settings live in `config.py`.

**Key components**
- `translator.py`: Main CLI entrypoint — orchestration for scanning source files, calling the LLM API, and writing outputs.
- `config.py`: Centralized configuration including paths, API key loading from `.env`, model selection, retry settings, and language mappings.
- `inspect_compact.py`, `inspect_doc.py`: Helper scripts for examining source templates and producing summarized metadata.
- `verify_images.py`: Utility to check input image sizes/format before translation.
- `test_*.py`: Unit/integration tests.
- `requirements.txt`: Python dependencies.
- `Translated Files/`: Local output folder (should be excluded from GitHub - see `.gitignore`).

## Architecture

The project follows a simple, single-process design:

- Configuration layer: `config.py` loads environment variables (via `.env`) and exposes constants used across modules.
- Orchestration layer: `translator.py` performs the high-level workflow — enumerate source files, call the API client (with retries), post-process responses and save results into `Translated Files/`.
- Helpers: small, single-responsibility scripts for inspection and verification tasks.
- Tests: pytest-based tests validating behavior.

This keeps the core translator minimal while allowing helper scripts to be run independently for debugging or preprocessing.

## Setup

1. Create and activate a Python virtual environment (recommended):

   - Windows (PowerShell):

     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the repository root with the API key (do not commit `.env` to GitHub):

   ```text
   CEREBRAS_API_KEY=your_api_key_here
   ```

4. Adjust `SOURCE_FOLDER` and `OUTPUT_FOLDER` in `config.py` or override them at runtime by editing the file or setting environment variables.

## Configuration

Open [config.py](config.py) to change behavior. Important settings:

- `CEREBRAS_API_KEY`: loaded from `.env` if present.
- `CEREBRAS_MODEL`: model identifier used for API calls.
- `SOURCE_FOLDER` / `OUTPUT_FOLDER`: file-system paths for input templates and outputs.
- `MAX_RETRIES` and `RETRY_DELAY`: control retry/backoff for remote calls.
- `LANGUAGE_MAP`: mapping of language codes to readable names.

## Running the translator

Run the main script. Example (from repository root):

```bash
python translator.py --all
```

See the script's help for additional CLI flags.

## Tests

Run tests with `pytest`:

```bash
pytest -q
```

## What to include on GitHub

Include the following files/folders in the GitHub repository:

- [translator.py](translator.py)
- [config.py](config.py)
- [requirements.txt](requirements.txt)
- [inspect_compact.py](inspect_compact.py)
- [inspect_doc.py](inspect_doc.py)
- [verify_images.py](verify_images.py)
- `test_*.py` files (unit/integration tests)
- `README.md` (this file)

Exclude the following (see `.gitignore`):

- `Translated Files/` (generated outputs)
- `.env` (API keys and secrets)
- `__pycache__/`, `.venv/`, `*.pyc`

## Security / Privacy

- Never commit API keys or `.env` files. Use CI secrets or repository secrets for deployment.
- Be careful with private data in source documents before uploading to remote services.

## Next steps (suggested)

- Verify `requirements.txt` lists only needed packages.
- Optionally create a minimal `pyproject.toml` for packaging.
- Ask me to prepare a commit and push to GitHub, or to add a GitHub Actions workflow to run tests.

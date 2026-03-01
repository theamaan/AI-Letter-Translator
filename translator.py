"""
AI Letter Translator — Agentic Document Translation Tool
=========================================================
Reads .docx healthcare letters, intelligently translates them using Cerebras AI,
preserving person names, IDs, formatting, and document alignment.
 
Usage:
    python translator.py                              # Translate one example file
    python translator.py --file "filename.docx"       # Translate a specific file
    python translator.py --all                        # Translate all files in source folder
 
Author: AI Translator Automation
"""
 
import argparse
import copy
import json
import os
import re
import sys
import time
from typing import Optional
 
from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt, Emu, RGBColor
from cerebras.cloud.sdk import Cerebras
 
import config
 
 
# ─── Cerebras Client ────────────────────────────────────────────────────────
def get_client() -> Cerebras:
    """Initialize the native Cerebras Cloud SDK client."""
    if not config.CEREBRAS_API_KEY:
        print("ERROR: CEREBRAS_API_KEY not set. Please update your .env file.")
        sys.exit(1)
    return Cerebras(api_key=config.CEREBRAS_API_KEY)
 
 
def call_llm(client: Cerebras, system_prompt: str, user_prompt: str) -> str:
    """Call the Cerebras LLM with retry logic using the native SDK."""
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            # Collect streamed response chunks
            stream = client.chat.completions.create(
                model=config.CEREBRAS_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                stream=True,
                max_completion_tokens=4096,
                temperature=0.1,  # Low temp for consistent, accurate translations
                top_p=1,
            )
            result = ""
            for chunk in stream:
                result += chunk.choices[0].delta.content or ""
            return result.strip()
        except Exception as e:
            wait = config.RETRY_DELAY ** attempt
            print(f"  [Retry {attempt}/{config.MAX_RETRIES}] API error: {e}. Waiting {wait}s...")
            time.sleep(wait)
    print("  ERROR: All API retries exhausted.")
    return ""
 
 
# ─── Filename Parsing ───────────────────────────────────────────────────────
def extract_language_code(filename: str) -> Optional[str]:
    """
    Extract the language code from the filename.
    E.g., 'MHWI Deny Your Request - OON_Member_..._es.docx' → 'es'
    """
    name_without_ext = os.path.splitext(filename)[0]
    # Split by underscore and get the last segment
    parts = name_without_ext.split("_")
    if parts:
        candidate = parts[-1].lower()
        if candidate in config.LANGUAGE_MAP:
            return candidate
    return None
 
 
def get_language_name(code: str) -> str:
    """Convert language code to full language name."""
    return config.LANGUAGE_MAP.get(code, code)
 
 
# ─── Document Structure Extraction ──────────────────────────────────────────
def consolidate_runs(paragraph):
    """
    Consolidate adjacent runs that have identical formatting into groups.
    Returns a list of dicts: [{text, runs_indices, formatting}, ...]
    Each group contains the combined text and the original run indices.
    """
    if not paragraph.runs:
        return []
 
    groups = []
    current_group = {
        "text": paragraph.runs[0].text,
        "run_indices": [0],
        "format_key": _run_format_key(paragraph.runs[0]),
    }
 
    for i in range(1, len(paragraph.runs)):
        run = paragraph.runs[i]
        fmt_key = _run_format_key(run)
        if fmt_key == current_group["format_key"]:
            # Same formatting — merge into current group
            current_group["text"] += run.text
            current_group["run_indices"].append(i)
        else:
            # Different formatting — start new group
            groups.append(current_group)
            current_group = {
                "text": run.text,
                "run_indices": [i],
                "format_key": fmt_key,
            }
    groups.append(current_group)
    return groups
def _run_format_key(run) -> str:
    """Generate a hashable formatting key for a run."""
    font = run.font
    parts = [
        str(font.bold),
        str(font.italic),
        str(font.underline),
        str(font.size),
        str(font.name),
        str(font.color.rgb if font.color and font.color.rgb else None),
    ]
    return "|".join(parts)
 
 
def extract_paragraph_text(paragraph) -> str:
    """Get full text of a paragraph from all its runs."""
    return "".join(run.text for run in paragraph.runs)


def extract_paragraph_elements(paragraph):
    """
    Extract all elements (runs and inline shapes) from a paragraph in order.
    Returns a list of dicts: {type: 'run'|'shape', content: run|shape}
    """
    elements = []
    # Iterate through the paragraph's XML elements to preserve order
    for elem in paragraph._element:
        if elem.tag.endswith('}r'):  # Run element
            # Find corresponding run object
            for run in paragraph.runs:
                if run._element == elem:
                    elements.append({'type': 'run', 'content': run})
                    break
        elif elem.tag.endswith('}pict') or elem.tag.endswith('}drawing'):  # Inline shape
            elements.append({'type': 'shape', 'content': copy.deepcopy(elem)})
    return elements


def preserve_inline_shapes(paragraph):
    """
    Save a complete snapshot of the paragraph XML that includes both
    text and shape elements. This helps ensure shapes are not lost.
    Returns both a list of shape elements and a deep copy of the element tree.
    """
    shapes = []
    shape_positions = []  # Track original positions
    
    for i, elem in enumerate(paragraph._element):
        if elem.tag.endswith('}pict') or elem.tag.endswith('}drawing'):
            shapes.append(copy.deepcopy(elem))
            shape_positions.append(i)
    
    return shapes, shape_positions


def restore_inline_shapes(paragraph, shapes, shape_positions):
    """
    Restore inline shapes to a paragraph at their original positions.
    Regenerates the paragraph element order to match the original structure.
    """
    if not shapes:
        return
    
    # Create a list of current elements
    current_elements = list(paragraph._element)
    
    # Remove all shape elements first (in reverse order to maintain indices)
    for i in range(len(current_elements) - 1, -1, -1):
        elem = current_elements[i]
        if elem.tag.endswith('}pict') or elem.tag.endswith('}drawing'):
            paragraph._element.remove(elem)
    
    # Re-add shapes at their original positions, if those positions still exist
    # Or append them at the end if the document structure changed
    for shape, original_pos in zip(shapes, shape_positions):
        try:
            # Try to insert at original position (accounting for removed shape elements)
            current_len = len(paragraph._element)
            if original_pos <= current_len:
                paragraph._element.insert(original_pos, shape)
            else:
                # Append if original position no longer exists
                paragraph._element.append(shape)
        except Exception:
            # Fallback: append at end
            paragraph._element.append(shape)


def _paragraph_has_shapes(paragraph):
    """Check if a paragraph contains any inline shapes/drawings."""
    for elem in paragraph._element.iter():
        tag = elem.tag.lower()
        if any(x in tag for x in ['shape', 'pict', 'drawing', 'blip', 'graphic', 'pic']):
            return True
    return False


def _translate_paragraph_simple(paragraph, target_language: str, do_not_translate: list[str], client: Cerebras):
    """
    Simple paragraph translation that modifies text in runs directly.
    SKIPS paragraphs containing shapes to protect logo preservation.
    """
    # Don't modify paragraphs that contain shapes - preserve them as-is
    if _paragraph_has_shapes(paragraph):
        return False
    
    para_text = extract_paragraph_text(paragraph)
    
    # Skip empty paragraphs
    if not para_text.strip():
        return False
    
    # Skip if only non-translatable
    if _is_only_non_translatable(para_text, do_not_translate):
        return False
    
    # Translate the entire paragraph text
    translated_text = translate_text_block(client, para_text, target_language, do_not_translate)
    
    if not translated_text:
        return False
    
    # Apply translation back: put all text in first run, clear the rest
    if paragraph.runs:
        paragraph.runs[0].text = translated_text
        # For other runs, set to empty to preserve structure
        for run in paragraph.runs[1:]:
            run.text = ""
    
    return True
 
 
# ─── Agentic Translation Logic ──────────────────────────────────────────────
 
ANALYSIS_SYSTEM_PROMPT = """You are an expert translation analyst for healthcare correspondence letters.
Your job is to analyze text from a healthcare letter and identify ALL elements that must NOT be translated.
 
These elements include:
- Person names (first name, last name, full names)
- Street addresses, city names, state abbreviations, ZIP codes
- Member ID numbers, reference numbers, case numbers
- Phone numbers, fax numbers
- Email addresses and website URLs
- Organization/company names (e.g., "Molina Healthcare", "BadgerCare Plus")
- Specific dates that are already formatted
- Medical codes (CPT, ICD, HCPCS codes)
- Legal case numbers or authorization numbers
- Acronyms that should remain in English (TTY, TDD, etc.)
 
Return your analysis as a JSON object with this exact structure:
{
  "do_not_translate": ["item1", "item2", ...],
  "reasoning": "Brief explanation of what you found"
}
 
Return ONLY the JSON object, no other text."""
 
def build_translation_prompt(target_language: str, do_not_translate: list[str]) -> str:
    """Build the system prompt for the translation pass."""
    dnt_list = "\n".join(f"  - {item}" for item in do_not_translate) if do_not_translate else "  (none identified)"
 
    return f"""You are an expert healthcare document translator. You translate English healthcare letters into {target_language}.
 
CRITICAL RULES:
1. Translate the text accurately and naturally into {target_language}.
2. Preserve the EXACT meaning — this is a legal/healthcare document.
3. DO NOT translate any of the following items — keep them EXACTLY as they appear:
{dnt_list}
4. DO NOT translate person names — keep them in their original form.
5. DO NOT translate organization names like "Molina Healthcare", "BadgerCare Plus", etc.
6. DO NOT translate phone numbers, fax numbers, email addresses, or URLs.
7. DO NOT translate member IDs, reference numbers, or medical codes.
8. DO NOT translate state abbreviations (WI, TN, CA, etc.) or ZIP codes.
9. Preserve all punctuation, parentheses, colons, and special characters.
10. If the text is ONLY whitespace, numbers, punctuation, or items from the do-not-translate list, return it UNCHANGED.
11. If the text is empty or consists only of formatting characters, return it UNCHANGED.
12. Return ONLY the translated text. Do NOT add explanations, notes, or extra content.
13. Do NOT wrap your response in quotes unless the original text had quotes.
 
IMPORTANT: Maintain the same tone (formal healthcare correspondence) and structure."""
 
 
def analyze_document_content(client: Cerebras, full_text: str) -> list[str]:
    """
    AGENT STEP 1: Analyze the full document to identify elements that should NOT
    be translated (names, IDs, addresses, etc.).
    """
    print("  [Agent Step 1] Analyzing document to identify non-translatable elements...")
 
    # Truncate if very long to stay within context window
    analysis_text = full_text[:6000] if len(full_text) > 6000 else full_text
 
    response = call_llm(client, ANALYSIS_SYSTEM_PROMPT, analysis_text)
 
    try:
        # Try to parse JSON from response
        # Handle cases where LLM wraps in markdown code blocks
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
       
        data = json.loads(cleaned)
        items = data.get("do_not_translate", [])
        reasoning = data.get("reasoning", "")
        print(f"  [Agent Step 1] Found {len(items)} non-translatable items.")
        if reasoning:
            print(f"  [Agent Step 1] Reasoning: {reasoning[:150]}")
        return items
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  [Agent Step 1] Warning: Could not parse analysis response: {e}")
        print(f"  [Agent Step 1] Falling back to default non-translatable items.")
        # Fallback: extract common patterns
        return _fallback_extract_non_translatable(full_text)
 
 
def _fallback_extract_non_translatable(text: str) -> list[str]:
    """Fallback regex-based extraction of non-translatable elements."""
    items = set()
    # Phone numbers
    for m in re.finditer(r"1[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}", text):
        items.add(m.group())
    # Email addresses
    for m in re.finditer(r"[\w.+-]+@[\w.-]+\.\w+", text):
        items.add(m.group())
    # URLs
    for m in re.finditer(r"https?://[^\s,)]+", text):
        items.add(m.group())
    # Known org names
    for org in ["Molina Healthcare", "BadgerCare Plus", "Molina"]:
        if org in text:
            items.add(org)
    return list(items)
 
 
def translate_text_block(
    client: Cerebras,
    text: str,
    target_language: str,
    do_not_translate: list[str],
) -> str:
    """
    AGENT STEP 2: Translate a single text block while preserving non-translatable items.
    """
    # Skip empty or whitespace-only text
    if not text or not text.strip():
        return text
 
    # Skip if text is only punctuation, numbers, or whitespace
    stripped = text.strip()
    if all(c in "0123456789.,;:!?()-–—/\\|#@$%^&*+=<>{}[]\"'`~ \t\n\r" for c in stripped):
        return text
 
    # Skip very short text that's likely a label or formatting artifact
    if len(stripped) <= 1:
        return text
 
    system_prompt = build_translation_prompt(target_language, do_not_translate)
    translated = call_llm(client, system_prompt, text)
 
    if not translated:
        print(f"    Warning: Empty translation for: '{text[:60]}...' — keeping original.")
        return text
 
    return translated
 
 
# ─── Document Processing (Formatting-Preserving) ────────────────────────────
 
def translate_document(
    source_path: str,
    output_path: str,
    target_language: str,
    client: Cerebras,
):
    """
    Main translation pipeline:
    1. Open the .docx and extract all text
    2. Agent analyzes content to find non-translatable elements
    3. Translate each paragraph while preserving run-level formatting
    4. Translate table cells
    5. Save the translated document
    """
    print(f"\n{'='*70}")
    print(f"Translating: {os.path.basename(source_path)}")
    print(f"Target language: {target_language}")
    print(f"{'='*70}")
 
    # Open document
    doc = Document(source_path)
 
    # Step 1: Extract all text for analysis
    all_text_parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            all_text_parts.append(para.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    all_text_parts.append(cell.text)
    full_text = "\n".join(all_text_parts)
 
    # Step 2: Agent analysis — identify non-translatable elements
    do_not_translate = analyze_document_content(client, full_text)
 
    # Step 3: Translate paragraphs
    total_paras = len(doc.paragraphs)
    translated_count = 0
    skipped_count = 0
 
    print(f"\n  [Agent Step 2] Translating {total_paras} paragraphs...")
 
    for i, para in enumerate(doc.paragraphs):
        # Use simple translation that doesn't consolidate runs or touch shapes
        if _translate_paragraph_simple(para, target_language, do_not_translate, client):
            translated_count += 1
        else:
            skipped_count += 1
        
        # Progress indicator every 10 paragraphs
        if (i + 1) % 10 == 0 or i == total_paras - 1:
            print(f"    Progress: {i+1}/{total_paras} paragraphs processed")
 
    # Step 4: Translate table cells
    print(f"\n  Translating {len(doc.tables)} table(s)...")
    for t_idx, table in enumerate(doc.tables):
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    _translate_paragraph_simple(para, target_language, do_not_translate, client)
 
    # Step 5: Translate headers and footers
    print("  Translating headers and footers...")
    for section in doc.sections:
        for header_footer in [section.header, section.footer]:
            if header_footer.is_linked_to_previous:
                continue
            for para in header_footer.paragraphs:
                _translate_paragraph_simple(para, target_language, do_not_translate, client)
 
    # Step 6: Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
 
    print(f"\n  DONE!")
    print(f"  Translated: {translated_count} paragraphs")
    print(f"  Skipped: {skipped_count} paragraphs (empty or non-translatable)")
    print(f"  Saved to: {output_path}")
    print(f"{'='*70}\n")
 
 
def _is_only_non_translatable(text: str, do_not_translate: list[str]) -> bool:
    """Check if text consists entirely of non-translatable items, whitespace, and punctuation."""
    remaining = text.strip()
    if not remaining:
        return True
 
    for item in do_not_translate:
        remaining = remaining.replace(item, "")
 
    # After removing all non-translatable items, check what's left
    remaining = remaining.strip()
    if not remaining:
        return True
 
    # If only punctuation, spaces, and numbers remain
    if all(c in ".,;:!?()-–—/\\|#@$%^&*+=<>{}[]\"'`~ \t\n\r0123456789" for c in remaining):
        return True
 
    return False
 
 
def _apply_translated_text_to_runs(paragraph, groups, translated_groups):
    """
    Apply translated text back into the paragraph's runs while preserving formatting.
   
    Strategy:
    - For each formatting group, replace the text across its constituent runs.
    - The first run in the group gets the translated text.
    - Remaining runs in the group are set to empty string (preserving their XML
      elements and formatting, but they'll render as nothing).
   
    This ensures all formatting (bold, italic, underline, font, size, color,
    alignment, spacing, etc.) is preserved exactly.
    """
    runs = paragraph.runs
    for group, translated_text in zip(groups, translated_groups):
        run_indices = group["run_indices"]
        if not run_indices:
            continue
 
        # Put all translated text into the first run of this group
        first_run_idx = run_indices[0]
        if first_run_idx < len(runs):
            runs[first_run_idx].text = translated_text
 
        # Clear the remaining runs in this group
        for idx in run_indices[1:]:
            if idx < len(runs):
                runs[idx].text = ""
 
 
# ─── CLI Entry Point ────────────────────────────────────────────────────────
 
def main():
    parser = argparse.ArgumentParser(
        description="AI Letter Translator — Translate .docx healthcare letters using Cerebras AI"
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Specific filename to translate (from the source folder)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="translate_all",
        help="Translate ALL files in the source folder",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files that already have translations in the output folder",
    )
    args = parser.parse_args()
 
    # Validate source folder
    if not os.path.exists(config.SOURCE_FOLDER):
        print(f"ERROR: Source folder not accessible: {config.SOURCE_FOLDER}")
        sys.exit(1)
 
    # Validate output folder
    os.makedirs(config.OUTPUT_FOLDER, exist_ok=True)
 
    # Initialize client
    client = get_client()
    print(f"Connected to Cerebras AI ({config.CEREBRAS_MODEL})")
 
    # Determine which files to translate
    if args.file:
        files_to_translate = [args.file]
    elif args.translate_all:
        files_to_translate = [
            f for f in os.listdir(config.SOURCE_FOLDER)
            if f.lower().endswith(".docx") and not f.startswith("~$")
        ]
    else:
        # Default: translate the first file with a language code
        files_to_translate = []
        for f in os.listdir(config.SOURCE_FOLDER):
            if f.lower().endswith(".docx") and not f.startswith("~$"):
                lang_code = extract_language_code(f)
                if lang_code:
                    files_to_translate.append(f)
                    break
        if not files_to_translate:
            print("No files with language codes found in the source folder.")
            sys.exit(1)
 
    print(f"\nFiles to translate: {len(files_to_translate)}")
 
    # Process each file
    success_count = 0
    error_count = 0
 
    for filename in files_to_translate:
        source_path = os.path.join(config.SOURCE_FOLDER, filename)
        output_path = os.path.join(config.OUTPUT_FOLDER, filename)
 
        # Skip if already exists and flag is set
        if args.skip_existing and os.path.exists(output_path):
            print(f"  Skipping (already exists): {filename}")
            continue
 
        # Extract language code
        lang_code = extract_language_code(filename)
        if not lang_code:
            print(f"  Skipping (no language code found): {filename}")
            continue
 
        target_language = get_language_name(lang_code)
 
        try:
            translate_document(source_path, output_path, target_language, client)
            success_count += 1
        except Exception as e:
            print(f"  ERROR translating {filename}: {e}")
            error_count += 1
 
    # Summary
    print(f"\n{'='*70}")
    print(f"TRANSLATION COMPLETE")
    print(f"  Successful: {success_count}")
    print(f"  Errors: {error_count}")
    print(f"  Output folder: {config.OUTPUT_FOLDER}")
    print(f"{'='*70}")
 
 
if __name__ == "__main__":
    main()

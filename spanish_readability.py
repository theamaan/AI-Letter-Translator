"""Spanish readability scoring and grade-target adaptation helpers.

This module is intentionally language-specific so future languages can add their
own root-level readability modules without bloating translator.py.
"""

from dataclasses import dataclass
import json
import re
from typing import Any, Optional


_VOWELS = set("aeiouaeiouyAEIOUAEIOUYáéíóúüÁÉÍÓÚÜ")
_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", re.UNICODE)
_SENTENCE_RE = re.compile(r"[.!?]+")


@dataclass(frozen=True)
class SpanishTargetBand:
    """Normalized target readability band used by adaptation logic."""

    label: str
    min_score: float
    max_score: float
    estimated_grade: str


@dataclass(frozen=True)
class SpanishReadabilityMetrics:
    """Fernandez-Huerta readability metrics for a Spanish text."""

    words: int
    sentences: int
    syllables: int
    score: float
    band: str
    estimated_grade: str


@dataclass(frozen=True)
class SpanishAdaptationResult:
    """Result of adapting Spanish text toward a requested grade target."""

    text: str
    before: SpanishReadabilityMetrics
    after: SpanishReadabilityMetrics
    target: SpanishTargetBand
    attempts: int
    reached_target: bool


@dataclass
class SpanishReadabilityTracker:
    """Aggregates paragraph-level adaptation outcomes into document-level stats."""

    target: SpanishTargetBand
    fragments: int = 0
    adapted_fragments: int = 0
    attempts_total: int = 0
    weighted_before_sum: float = 0.0
    weighted_after_sum: float = 0.0
    weighted_words: int = 0

    def record(self, result: SpanishAdaptationResult) -> None:
        self.fragments += 1
        if result.attempts > 0:
            self.adapted_fragments += 1
        self.attempts_total += result.attempts

        weight = max(result.after.words, 1)
        self.weighted_words += weight
        self.weighted_before_sum += result.before.score * weight
        self.weighted_after_sum += result.after.score * weight

    def summary(self) -> Optional[dict]:
        if self.fragments == 0 or self.weighted_words == 0:
            return None

        avg_before = self.weighted_before_sum / self.weighted_words
        avg_after = self.weighted_after_sum / self.weighted_words

        return {
            "target_label": self.target.label,
            "target_range": f"{self.target.min_score:.1f}-{self.target.max_score:.1f}",
            "target_estimated_grade": self.target.estimated_grade,
            "fragments": self.fragments,
            "adapted_fragments": self.adapted_fragments,
            "attempts_total": self.attempts_total,
            "avg_before_score": round(avg_before, 2),
            "avg_after_score": round(avg_after, 2),
            "avg_after_band": score_to_band(avg_after),
            "avg_after_estimated_grade": score_to_estimated_grade(avg_after),
            "target_reached_on_average": _score_in_target(avg_after, self.target),
        }


def normalize_target_grade(target: Any) -> SpanishTargetBand:
    """Normalize target grade input into a score band.

    Accepted forms:
      - Numeric grade: 5, 7, 9, 11
      - Numeric string: "6", "8"
            - Named band: "very easy", "easy", "normal", "moderate", "difficult"
    """
    if target is None:
        raise ValueError("Spanish target grade is required for normalization.")

    if isinstance(target, (int, float)):
        return _band_from_numeric_grade(float(target))

    if isinstance(target, str):
        raw = target.strip().lower()
        if not raw:
            raise ValueError("Spanish target grade cannot be empty.")

        numeric = _try_parse_numeric(raw)
        if numeric is not None:
            return _band_from_numeric_grade(numeric)

        aliases = {
            "very easy": "very-easy",
            "very_easy": "very-easy",
            "easy": "easy",
            "normal": "normal",
            "standard": "normal",
            "moderate": "moderate",
            "medium": "moderate",
            "difficult": "difficult",
            "hard": "difficult",
            "grade 5": "very-easy",
            "grade 6": "easy",
            "grade 7": "easy",
            "grade 8": "normal",
            "grade 9": "normal",
            "grade 10": "moderate",
            "grade 11": "moderate",
            "grade 12": "moderate",
        }
        norm = aliases.get(raw, raw.replace("_", "-").replace(" ", "-"))

        if norm == "very-easy":
            return SpanishTargetBand("very-easy", 90.0, 100.0, "Grade 5 or lower")
        if norm == "easy":
            return SpanishTargetBand("easy", 80.0, 89.99, "Grade 6-7")
        if norm == "normal":
            return SpanishTargetBand("normal", 60.0, 79.99, "Grade 8-9")
        if norm == "moderate":
            return SpanishTargetBand("moderate", 50.0, 59.99, "Grade 10-12")
        if norm == "difficult":
            return SpanishTargetBand("difficult", 0.0, 49.99, "High school/college+")

    raise ValueError(
        "Unsupported Spanish target grade. Use numeric grades (e.g., 6, 8) "
        "or bands: very easy, easy, normal, moderate, difficult."
    )


def compute_fernandez_huerta(text: str) -> SpanishReadabilityMetrics:
    """Compute Fernandez-Huerta score and interpretation for Spanish text."""
    words = _count_words(text)
    if words == 0:
        return SpanishReadabilityMetrics(
            words=0,
            sentences=0,
            syllables=0,
            score=0.0,
            band="difficult",
            estimated_grade="Insufficient text",
        )

    sentences = _count_sentences(text)
    syllables = _count_syllables(text)

    syllables_per_100 = (syllables / words) * 100.0
    sentences_per_100 = (sentences / words) * 100.0

    score = 206.84 - (0.60 * syllables_per_100) - (1.02 * sentences_per_100)
    score = max(0.0, min(100.0, score))

    return SpanishReadabilityMetrics(
        words=words,
        sentences=sentences,
        syllables=syllables,
        score=round(score, 2),
        band=score_to_band(score),
        estimated_grade=score_to_estimated_grade(score),
    )


def adapt_spanish_text_to_grade(
    text: str,
    target: SpanishTargetBand,
    router,
    do_not_translate: list,
    max_attempts: int = 3,
    min_words_for_adapt: int = 12,
) -> SpanishAdaptationResult:
    """Adapt Spanish text to a target readability band using bounded retries."""
    before = compute_fernandez_huerta(text)

    if before.words < min_words_for_adapt:
        return SpanishAdaptationResult(
            text=text,
            before=before,
            after=before,
            target=target,
            attempts=0,
            reached_target=_score_in_target(before.score, target),
        )

    best_text = text
    best_metrics = before
    best_distance = _distance_to_target(before.score, target)

    attempts = 0
    while attempts < max_attempts and not _score_in_target(best_metrics.score, target):
        attempts += 1
        system_prompt = _build_spanish_adaptation_prompt(target, do_not_translate)
        rewritten, _label = router.call_with_fallback("translate", system_prompt, best_text)
        if not rewritten or not rewritten.strip():
            break

        candidate = rewritten.strip()
        candidate_metrics = compute_fernandez_huerta(candidate)
        candidate_distance = _distance_to_target(candidate_metrics.score, target)

        if candidate_distance <= best_distance:
            best_text = candidate
            best_metrics = candidate_metrics
            best_distance = candidate_distance

        if _score_in_target(candidate_metrics.score, target):
            best_text = candidate
            best_metrics = candidate_metrics
            break

    return SpanishAdaptationResult(
        text=best_text,
        before=before,
        after=best_metrics,
        target=target,
        attempts=attempts,
        reached_target=_score_in_target(best_metrics.score, target),
    )


def score_to_band(score: float) -> str:
    if score >= 90:
        return "very-easy"
    if score >= 80:
        return "easy"
    if score >= 60:
        return "normal"
    if score >= 50:
        return "moderate"
    return "difficult"


def score_to_estimated_grade(score: float) -> str:
    if score >= 90:
        return "Grade 5 or lower"
    if score >= 80:
        return "Grade 6-7"
    if score >= 60:
        return "Grade 8-9"
    if score >= 50:
        return "Grade 10-12"
    return "High school/college+"


def _count_words(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def _count_sentences(text: str) -> int:
    count = len(_SENTENCE_RE.findall(text or ""))
    return max(count, 1) if (text or "").strip() else 0


def _count_syllables(text: str) -> int:
    total = 0
    for word in _WORD_RE.findall(text or ""):
        total += _estimate_syllables_word(word)
    return total


def _estimate_syllables_word(word: str) -> int:
    # Basic Spanish heuristic: number of vowel groups ~= syllable count.
    cleaned = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", word)
    if not cleaned:
        return 0

    syllables = 0
    prev_vowel = False
    for ch in cleaned:
        is_vowel = ch in _VOWELS
        if is_vowel and not prev_vowel:
            syllables += 1
        prev_vowel = is_vowel

    return max(syllables, 1)


def _try_parse_numeric(raw: str) -> Optional[float]:
    if not re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return None
    return float(raw)


def _band_from_numeric_grade(grade: float) -> SpanishTargetBand:
    if grade <= 5:
        return SpanishTargetBand("very-easy", 90.0, 100.0, "Grade 5 or lower")
    if grade <= 7:
        return SpanishTargetBand("easy", 80.0, 89.99, "Grade 6-7")
    if grade <= 9:
        return SpanishTargetBand("normal", 60.0, 79.99, "Grade 8-9")
    if grade <= 12:
        return SpanishTargetBand("moderate", 50.0, 59.99, "Grade 10-12")
    return SpanishTargetBand("difficult", 0.0, 49.99, "High school/college+")


def _score_in_target(score: float, target: SpanishTargetBand) -> bool:
    return target.min_score <= score <= target.max_score


def _distance_to_target(score: float, target: SpanishTargetBand) -> float:
    if _score_in_target(score, target):
        return 0.0
    if score < target.min_score:
        return target.min_score - score
    return score - target.max_score


def _build_spanish_adaptation_prompt(target: SpanishTargetBand, do_not_translate: list) -> str:
    dnt_compact = json.dumps(do_not_translate[:30], ensure_ascii=False) if do_not_translate else "[]"
    return (
        "Reescribe el siguiente texto en espanol para mejorar su adecuacion de lectura. "
        f"Objetivo de legibilidad Fernandez-Huerta: {target.min_score:.1f} a {target.max_score:.1f} "
        f"(nivel estimado: {target.estimated_grade}). "
        "Mantener significado legal/clinico exacto, tono formal y terminologia esencial. "
        f"NO traducir ni alterar estos elementos: {dnt_compact}. "
        "Devuelve solo el texto final reescrito, sin notas ni explicaciones."
    )

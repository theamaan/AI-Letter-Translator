"""Unit tests for Spanish readability scoring and adaptation."""

import unittest

from spanish_readability import (
    SpanishReadabilityTracker,
    adapt_spanish_text_to_grade,
    compute_fernandez_huerta,
    normalize_target_grade,
)


class _FakeRouter:
    def __init__(self, outputs):
        self._outputs = list(outputs)

    def call_with_fallback(self, task_type, system_prompt, text):
        if self._outputs:
            return self._outputs.pop(0), "ollama"
        return text, "ollama"


class SpanishReadabilityTests(unittest.TestCase):
    def test_normalize_target_grade_numeric(self):
        target = normalize_target_grade(6)
        self.assertEqual(target.label, "easy")
        self.assertGreaterEqual(target.min_score, 80.0)

    def test_normalize_target_grade_band_alias(self):
        target = normalize_target_grade("very easy")
        self.assertEqual(target.label, "very-easy")
        self.assertEqual(target.estimated_grade, "Grade 5 or lower")

    def test_fernandez_huerta_scores_simpler_text_higher(self):
        simple = "Este texto es simple. Tiene frases cortas. Es facil de leer."
        complex_text = (
            "No obstante, la determinacion administrativa previamente notificada "
            "requiere una reconsideracion exhaustiva de los criterios de cobertura "
            "aplicables segun las disposiciones clinicas correspondientes."
        )

        simple_score = compute_fernandez_huerta(simple).score
        complex_score = compute_fernandez_huerta(complex_text).score
        self.assertGreater(simple_score, complex_score)

    def test_adaptation_attempts_toward_target(self):
        original = (
            "No obstante, la determinacion administrativa previamente notificada "
            "requiere una reconsideracion exhaustiva de los criterios de cobertura "
            "aplicables segun las disposiciones clinicas correspondientes."
        )
        rewritten_easy = "Su solicitud fue revisada. Esta carta explica la decision con palabras claras."

        target = normalize_target_grade("easy")
        router = _FakeRouter([rewritten_easy])

        result = adapt_spanish_text_to_grade(
            text=original,
            target=target,
            router=router,
            do_not_translate=[],
            max_attempts=2,
            min_words_for_adapt=1,
        )

        self.assertGreaterEqual(result.attempts, 1)
        self.assertGreaterEqual(result.after.score, result.before.score)

    def test_tracker_summary_populated(self):
        text = "Este texto es corto pero claro."
        target = normalize_target_grade("normal")
        router = _FakeRouter([text])

        result = adapt_spanish_text_to_grade(
            text=text,
            target=target,
            router=router,
            do_not_translate=[],
            max_attempts=1,
            min_words_for_adapt=1,
        )

        tracker = SpanishReadabilityTracker(target)
        tracker.record(result)
        summary = tracker.summary()

        self.assertIsNotNone(summary)
        self.assertEqual(summary["fragments"], 1)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Spanish dispatch hooks in translator."""

import unittest
from unittest.mock import patch

import config
from spanish_readability import normalize_target_grade
from translator import _cache_key, _maybe_adapt_spanish_text


class _DummyRouter:
    def call_with_fallback(self, task_type, system_prompt, text):
        return text, "ollama"


class TranslatorSpanishHookTests(unittest.TestCase):
    def test_cache_key_includes_spanish_target(self):
        target = normalize_target_grade("easy")
        key = _cache_key("Hola mundo", "Spanish", target)
        self.assertEqual(len(key), 3)
        self.assertIn("spanish-target:easy", key)

    def test_cache_key_non_spanish_unchanged(self):
        target = normalize_target_grade("easy")
        key = _cache_key("Hello world", "French", target)
        self.assertEqual(len(key), 2)

    def test_spanish_adaptation_called_only_for_spanish(self):
        target = normalize_target_grade("normal")

        with patch("translator.adapt_spanish_text_to_grade") as mock_adapt:
            mock_adapt.return_value.text = "texto adaptado"
            with patch.object(config, "SPANISH_READABILITY_ENABLED", True):
                out = _maybe_adapt_spanish_text(
                    translated_text="texto base",
                    target_language="Spanish",
                    do_not_translate=[],
                    router=_DummyRouter(),
                    spanish_target=target,
                    spanish_tracker=None,
                )

        self.assertEqual(out, "texto adaptado")
        self.assertEqual(mock_adapt.call_count, 1)

    def test_non_spanish_bypasses_adaptation(self):
        target = normalize_target_grade("normal")

        with patch("translator.adapt_spanish_text_to_grade") as mock_adapt:
            with patch.object(config, "SPANISH_READABILITY_ENABLED", True):
                out = _maybe_adapt_spanish_text(
                    translated_text="texte de base",
                    target_language="French",
                    do_not_translate=[],
                    router=_DummyRouter(),
                    spanish_target=target,
                    spanish_tracker=None,
                )

        self.assertEqual(out, "texte de base")
        self.assertEqual(mock_adapt.call_count, 0)


if __name__ == "__main__":
    unittest.main()

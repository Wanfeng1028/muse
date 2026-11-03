"""Unit tests for the word-pause duck envelope in scripts/synth_audio.py: parsing and gap detection."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import synth_audio


def words_js(phrases):
    return "window.PHRASES=" + json.dumps(phrases) + ";"


def word(text, start, end):
    return {"t": text, "s": start, "e": end}


class ParseWordsJsTest(unittest.TestCase):
    def test_should_read_word_times_out_of_the_assignment_wrapper(self):
        text = words_js([[word("hi", 0.0, 0.5), word("there", 0.6, 1.0)], [word("friend", 3.0, 3.4)]])
        self.assertEqual(synth_audio.parse_words_js(text), [(0.0, 0.5), (0.6, 1.0), (3.0, 3.4)])

    def test_should_tolerate_a_trailing_newline_and_no_semicolon(self):
        text = words_js([[word("hi", 1.0, 1.5)]])[:-1] + "\n"
        self.assertEqual(synth_audio.parse_words_js(text), [(1.0, 1.5)])

    def test_should_sort_words_that_arrive_out_of_order(self):
        text = words_js([[word("later", 5.0, 5.5)], [word("first", 0.0, 0.4)]])
        self.assertEqual(synth_audio.parse_words_js(text), [(0.0, 0.4), (5.0, 5.5)])

    def test_should_skip_entries_without_numeric_times(self):
        phrases = [[word("ok", 0.0, 0.5), {"t": "odd", "s": "soon"}, {"t": "empty"}]]
        self.assertEqual(synth_audio.parse_words_js(words_js(phrases)), [(0.0, 0.5)])

    def test_should_return_none_for_text_that_is_not_a_word_array(self):
        self.assertIsNone(synth_audio.parse_words_js("window.PHRASES=not json;"))
        self.assertIsNone(synth_audio.parse_words_js("no assignment here"))


class DuckGapsTest(unittest.TestCase):
    def test_should_find_a_pause_between_consecutive_words(self):
        words = [(0.0, 0.5), (2.0, 2.5)]
        self.assertEqual(synth_audio.duck_gaps(words, 10.0), [[0.5, 2.0]])

    def test_should_ignore_a_pause_shorter_than_the_minimum(self):
        words = [(0.0, 0.5), (1.0, 1.5)]
        self.assertEqual(synth_audio.duck_gaps(words, 10.0), [])

    def test_should_accept_a_pause_exactly_at_the_minimum(self):
        words = [(0.0, 0.5), (1.1, 1.5)]
        self.assertEqual(synth_audio.duck_gaps(words, 10.0), [[0.5, 1.1]])

    def test_should_clamp_a_pause_to_the_duration(self):
        words = [(9.5, 9.8), (12.0, 12.5)]
        self.assertEqual(synth_audio.duck_gaps(words, 10.0), [[9.8, 10.0]])

    def test_should_drop_a_pause_fully_outside_the_duration(self):
        words = [(10.0, 10.5), (12.0, 12.5)]
        self.assertEqual(synth_audio.duck_gaps(words, 10.0), [])

    def test_should_return_nothing_for_fewer_than_two_words(self):
        self.assertEqual(synth_audio.duck_gaps([], 10.0), [])
        self.assertEqual(synth_audio.duck_gaps([(0.0, 0.5)], 10.0), [])

    def test_should_find_every_qualifying_pause(self):
        words = [(0.0, 0.2), (1.0, 1.2), (1.3, 1.5), (3.0, 3.2)]
        self.assertEqual(synth_audio.duck_gaps(words, 10.0), [[0.2, 1.0], [1.5, 3.0]])


class BuildDuckExprTest(unittest.TestCase):
    def test_expression_grows_linearly_with_gaps(self):
        # the previous nested form doubled per gap: 17 real-world gaps blew past ARG_MAX mid-mix
        expr = synth_audio.build_duck_expr([[i * 3.0, i * 3.0 + 1.0] for i in range(100)], 0.18)
        self.assertLess(len(expr), 50_000)

    def test_each_gap_appears_once(self):
        expr = synth_audio.build_duck_expr([[1.0, 2.0], [5.0, 6.0]], 0.18)
        self.assertEqual(expr.count("5.000"), 2)  # start and ramped edge of the second window only

    def test_no_gaps_or_full_or_zero_level_gives_no_expression(self):
        self.assertIsNone(synth_audio.build_duck_expr([], 0.18))
        self.assertIsNone(synth_audio.build_duck_expr([[1.0, 2.0]], 1.0))
        self.assertIsNone(synth_audio.build_duck_expr([[1.0, 2.0]], 0.0))
        self.assertIsNone(synth_audio.build_duck_expr([[1.0, 2.0]], "loud"))

    def test_gaps_shorter_than_two_ramps_are_skipped(self):
        self.assertIsNone(synth_audio.build_duck_expr([[1.0, 1.2]], 0.18))


if __name__ == "__main__":
    unittest.main()

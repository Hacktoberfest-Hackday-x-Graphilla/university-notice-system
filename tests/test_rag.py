"""Tests for the RAG logic (rag.py). No API calls, no web server."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rag


class ChunkTests(unittest.TestCase):
    def test_short_text_stays_one_chunk(self):
        chunks = rag.chunk_text("Short notice about office hours.")
        self.assertEqual(len(chunks), 1)

    def test_long_text_splits_into_chunks(self):
        text = ("Paragraph one. " * 20 + "\n\n" + "Paragraph two. " * 20) * 8
        chunks = rag.chunk_text(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), rag.MAX_CHUNK_CHARS + rag.CHUNK_OVERLAP)

    def test_empty_text_has_no_chunks(self):
        self.assertEqual(rag.chunk_text("   \n\n  "), [])


class IndexAndRetrieveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_index_file = rag.INDEX_FILE
        rag.INDEX_FILE = Path(self.tmp.name) / "index.json"
        rag.forget_all()

    def tearDown(self):
        rag.INDEX_FILE = self.old_index_file

    def _store(self, source, text):
        chunks = rag.load_index()
        chunks.append({"source": source, "text": text})
        rag.save_index(chunks)

    def test_roundtrip_and_forget(self):
        self._store("a.pdf", "hello")
        self.assertEqual(len(rag.load_index()), 1)
        rag.forget_all()
        self.assertEqual(rag.load_index(), [])

    def test_retrieve_ranks_relevant_chunk_first(self):
        self._store(
            "office.pdf",
            "The office opens at 10:00 and closes at 17:00 every working day.",
        )
        self._store(
            "parking.pdf",
            "Visitors must park in the blue zone near the main gate.",
        )
        results = rag.retrieve("what time does the office open")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "office.pdf")

    def test_retrieve_ignores_stopword_only_queries(self):
        self._store("office.pdf", "The office opens at 10:00.")
        self.assertEqual(rag.retrieve("the and of it"), [])

    def test_list_sources_is_sorted_and_unique(self):
        self._store("b.pdf", "note one")
        self._store("a.pdf", "note two")
        self._store("b.pdf", "note three")
        self.assertEqual(rag.list_sources(), ["a.pdf", "b.pdf"])


class AskTests(unittest.TestCase):
    def test_ask_with_no_matching_docs_returns_friendly_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = rag.INDEX_FILE
            rag.INDEX_FILE = Path(tmp) / "index.json"
            try:
                rag.forget_all()
                answer, sources = rag.ask("what time does the office open")
            finally:
                rag.INDEX_FILE = old
        self.assertEqual(sources, [])
        self.assertIn("upload", answer.lower())


if __name__ == "__main__":
    unittest.main()
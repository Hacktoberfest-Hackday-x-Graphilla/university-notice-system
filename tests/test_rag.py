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

    def test_devanagari_query_matches_devanagari_chunk(self):
        self._store("office.pdf", "The office opens at 10:00.")
        self._store(
            "tu.pdf",
            "त्रिभुवन विश्वविद्यालय परीक्षा नतिजा प्रकाशन सम्बन्धी सूचना",
        )
        results = rag.retrieve("सूचना के हो")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "tu.pdf")

    def test_no_match_falls_back_to_recent_chunks(self):
        # An English question over a Nepali-only document should still get
        # material to answer from, not an empty retrieval.
        self._store("old.pdf", "old english note")
        self._store("tu.pdf", "विज्ञान तथा प्रविधि परीक्षा नतिजा")
        results = rag.retrieve("summarize the notice")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "tu.pdf")  # most recent first


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


class PdfReadTests(unittest.TestCase):
    """Text-layer reading + vision fallback (transcription is mocked, no API)."""

    SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample-notice.pdf"

    def _make_image_only_pdf(self, path: Path) -> None:
        """A PDF whose text is pixels only (like a phone scan)."""
        import pymupdf as fitz

        src = fitz.open()
        sp = src.new_page()
        sp.insert_text((72, 72), "SCANNED OFFICE NOTICE opens at 10:00 daily")
        pix = sp.get_pixmap(matrix=fitz.Matrix(2, 2))
        doc = fitz.open()
        page = doc.new_page(width=pix.width, height=pix.height)
        page.insert_image(page.rect, pixmap=pix)
        doc.save(path)
        doc.close()
        src.close()

    def test_text_layer_pdf_reads_without_api(self):
        text = rag.get_document_text(self.SAMPLE)
        self.assertIn("office", text.lower())
        self.assertTrue(rag.readable_text(text))

    def test_image_only_pdf_has_no_text_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.pdf"
            self._make_image_only_pdf(path)
            self.assertFalse(rag.readable_text(rag.extract_pdf_text(path)))

    def test_render_pdf_pages_returns_pngs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.pdf"
            self._make_image_only_pdf(path)
            pages = rag.render_pdf_pages(path)
            self.assertGreaterEqual(len(pages), 1)
            self.assertTrue(pages[0].startswith(b"\x89PNG"))

    def test_vision_fallback_transcribes_scanned_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.pdf"
            self._make_image_only_pdf(path)
            calls = []

            def fake_transcribe(pages):
                calls.append(len(pages))
                self.assertGreater(len(pages), 0)
                return "The scanned office notice says the office opens at 10:00."

            original = rag.transcribe_pages
            rag.transcribe_pages = fake_transcribe
            try:
                text = rag.get_document_text(path)
            finally:
                rag.transcribe_pages = original
        self.assertIn("10:00", text)
        self.assertEqual(len(calls), 1)

    def test_vision_fallback_raises_when_transcription_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.pdf"
            self._make_image_only_pdf(path)
            original = rag.transcribe_pages
            rag.transcribe_pages = lambda pages: ""
            try:
                with self.assertRaises(ValueError):
                    rag.get_document_text(path)
            finally:
                rag.transcribe_pages = original


if __name__ == "__main__":
    unittest.main()
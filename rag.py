"""rag.py - the chatbot brain: turn uploaded PDF notices into answers.

Kept separate from app.py so the logic can be tested without a web server,
and so a contributor can improve retrieval/answers without touching Flask.

How it works:
  upload -> read the text (embedded text layer, or a Gemma vision pass
            for scanned PDFs) -> split into chunks -> saved in data/index.json
  question -> pick the few most relevant chunks (simple word match)
           -> send them + the question to a Google AI Studio model (Gemma)
           -> return the answer and which files it came from.
"""

import json
import os
import re
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # the key can also be exported in the shell instead
    pass

REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
INDEX_FILE = DATA_DIR / "index.json"
MODEL = os.environ.get("GEMINI_MODEL", "gemma-4-26b-a4b-it")

MAX_CHUNK_CHARS = 900
CHUNK_OVERLAP = 100
TOP_K = 4
MIN_TEXT_CHARS = 30  # below this a PDF counts as scanned / unreadable

# Vision fallback (scanned PDFs): render pages and let the model read them.
VISION_DPI = 200
VISION_MAX_PAGES = 3
MAX_RENDER_PIXELS = 30_000_000

# Small words that don't help pick relevant chunks.
STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "for", "on", "in", "is", "are",
    "was", "were", "be", "has", "have", "had", "do", "does", "did", "with",
    "at", "by", "from", "as", "it", "its", "this", "that", "these", "those",
    "i", "you", "he", "she", "we", "they", "my", "your", "his", "her", "our",
    "their", "will", "can", "could", "should", "would", "about", "please",
}


# ---------------------------------------------------------------------------
# Index persistence (data/index.json, gitignored)
# ---------------------------------------------------------------------------
def load_index() -> list:
    if not INDEX_FILE.is_file():
        return []
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def save_index(chunks: list) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def forget_all() -> None:
    save_index([])


def list_sources() -> list:
    return sorted({chunk["source"] for chunk in load_index()})


# ---------------------------------------------------------------------------
# PDF -> text -> chunks
# ---------------------------------------------------------------------------
def extract_pdf_text(path: Path) -> str:
    """Read a PDF's embedded text layer. May be empty/short for scanned PDFs."""
    import pymupdf as fitz

    doc = fitz.open(path)
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


def render_pdf_pages(path: Path) -> list:
    """Render pages of a scanned PDF as PNG bytes for the model (vision)."""
    import pymupdf as fitz

    doc = fitz.open(path)
    try:
        pages = []
        for page in list(doc)[:VISION_MAX_PAGES]:
            width = max(page.rect.width, 1) * (VISION_DPI / 72)
            height = max(page.rect.height, 1) * (VISION_DPI / 72)
            scale = 1.0
            if width * height > MAX_RENDER_PIXELS:  # keep huge pages within limits
                scale = (MAX_RENDER_PIXELS / (width * height)) ** 0.5
            pix = page.get_pixmap(
                matrix=fitz.Matrix(VISION_DPI / 72 * scale, VISION_DPI / 72 * scale)
            )
            pages.append(pix.tobytes("png"))
        return pages
    finally:
        doc.close()


def transcribe_pages(pages: list) -> str:
    """Ask the model to read page images and return the text they contain."""
    from google.genai import types

    client = _client()
    parts = [types.Part.from_bytes(data=png, mime_type="image/png") for png in pages]
    prompt = (
        "Transcribe all the text on these document pages exactly as written. "
        "Keep the paragraphs and numbers as they appear. "
        "Write only the transcribed text, with no commentary."
    )
    response = client.models.generate_content(model=MODEL, contents=[*parts, prompt])
    return (response.text or "").strip()


def readable_text(text: str) -> bool:
    """Enough non-space characters to be useful as a real document."""
    return len(re.sub(r"\s", "", text)) >= MIN_TEXT_CHARS


def get_document_text(path: Path) -> str:
    """Best-effort reading: embedded text layer first, vision fallback for scans.

    Scanned (image-only) PDFs have no text layer, so we render the pages and
    let the model transcribe them. Raises ValueError if nothing can be read.
    """
    text = extract_pdf_text(path)
    if readable_text(text):
        return text
    pages = render_pdf_pages(path)
    if not pages:
        raise ValueError("could not read this PDF (no text layer and no pages)")
    transcription = transcribe_pages(pages)
    if not readable_text(transcription):
        raise ValueError(
            "could not read this PDF - the vision pass returned no usable text "
            "(check GEMINI_API_KEY and try again)"
        )
    return transcription


def chunk_text(text: str, size: int = MAX_CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list:
    """Split a long text into overlapping chunks so questions can find the part
    that matters. Empty chunks are dropped."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        if end < length:
            cut = text.rfind("\n", start, end)  # try to break at a paragraph end
            if cut > start + size // 2:
                end = cut
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks


def index_document(path: Path) -> int:
    """Add one PDF to the index. Returns how many chunks were stored."""
    if path.suffix.lower() != ".pdf":
        raise ValueError("only PDF files are supported")
    chunks = load_index()
    pieces = chunk_text(get_document_text(path))
    for piece in pieces:
        chunks.append({"source": path.name, "text": piece})
    save_index(chunks)
    return len(pieces)


# ---------------------------------------------------------------------------
# Find relevant chunks + answer
# ---------------------------------------------------------------------------
# Tokens: ASCII words + Devanagari letters/marks (Nepali notices are common).
# Without the Devanagari block, Nepali words like 'सूचना' would split on
# combining marks and never match a query.
DEVANAGARI = "\u0900-\u097F"
TOKEN_RE = re.compile(r"[a-z0-9_" + DEVANAGARI + r"]+")


def _tokens(text: str) -> list:
    words = TOKEN_RE.findall(text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def retrieve(query: str, top_k: int = TOP_K) -> list:
    """Return the most relevant chunks for a question (word-match ranking)."""
    words = _tokens(query)
    if not words:
        return []
    scored = []
    for chunk in load_index():
        hay = set(_tokens(chunk["text"]))
        hits = sum(1 for w in words if w in hay)
        if hits:
            scored.append((hits, chunk))
    if scored:
        scored.sort(key=lambda pair: (-pair[0], len(pair[1]["text"])))
        return [chunk for _, chunk in scored[:top_k]]
    # Nothing matched (e.g. the question is in a different language than the
    # documents). Fall back to the most recently uploaded chunks so the model
    # still has real material to read instead of answering from nothing.
    return load_index()[-top_k:][::-1]


def _client():
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY not found - copy .env.example to .env, add your key, and re-run."
        )
    from google import genai

    return genai.Client()  # reads GEMINI_API_KEY from the environment


def _call_model(prompt: str) -> str:
    client = _client()
    response = client.models.generate_content(model=MODEL, contents=prompt)
    return response.text.strip()


def ask(question: str) -> tuple:
    """Answer a question from the uploaded excerpts.

    Returns (answer_text, sources) where sources is a sorted list of file
    names the answer was built from.
    """
    results = retrieve(question)
    if not results:
        return (
            "I could not find anything relevant in the uploaded documents yet. "
            "Upload a notice PDF first, then ask again.",
            [],
        )
    excerpts = "\n\n".join(
        f"[{i + 1}] (from {chunk['source']}) {chunk['text']}"
        for i, chunk in enumerate(results)
    )
    prompt = (
        "You answer questions using ONLY the document excerpts below "
        "(they come from uploaded notice PDFs).\n"
        "If the answer is not in the excerpts, say so plainly - do not guess.\n\n"
        f"Excerpts:\n{excerpts}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )
    answer = _call_model(prompt)
    return answer, sorted({chunk["source"] for chunk in results})
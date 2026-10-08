# Notice Chat — a simple RAG chatbot for PDF notices

Upload **notice PDFs**, then chat: the bot answers your questions **using only
the documents you uploaded**. A simple retrieval-augmented (RAG) chatbot:
it finds the relevant parts of your notices and lets a Gemma model answer
from them — no training, no internet knowledge, no hallucinating beyond the docs.

**Status: just started.** The basic chatbot works; contributors make it better.

## Try it

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and put your Google AI Studio API key in
`GEMINI_API_KEY`, and set `ADMIN_PASSWORD` to whatever you want the upload
password to be. `.env` is gitignored, so it never leaves your machine.

```bash
python app.py
```

Open two pages:

- **http://127.0.0.1:5000/** — the public chatbot. Ask anything, no password.
- **http://127.0.0.1:5000/admin** — the admin page. Enter the **admin
  password** (from `ADMIN_PASSWORD` in your `.env`), upload a notice PDF
  (try [`examples/sample-notice.pdf`](examples/sample-notice.pdf)), or
  forget all documents.

Then go back to the chat and ask something like *"What time does the office
open?"*

**Who can do what:** uploading and resetting happen on `/admin` and need
the `ADMIN_PASSWORD` from `.env`. Asking questions on `/` is open to
everyone — no password needed.

## How it works (in one line each)

| File | Job |
|---|---|
| `app.py` | the web server + endpoints; upload is admin-only, asking is open (the **backend**) |
| `rag.py` | turns PDFs into chunks, finds the relevant ones, asks the model |
| `static/index.html` | the public chat page (the **frontend**) |
| `static/admin.html` | the admin page: upload + reset documents |
| `data/` | local storage for uploads + the index (created on first run, gitignored) |

Flow: upload → PDF text is split into chunks → your question picks the few
most relevant chunks (simple word match) → a Gemma model answers using only
those chunks + name of the file it came from.

Only PDFs with a text layer are read for now (scanned/image-only PDFs are a
known limitation). Uploads and the index live in your local `data/` folder —
nothing personal is committed.

## Contribute — 3 steps, no pressure

1. Open the **Issues** tab.
2. Pick any issue labelled `beginner` or `good first issue`.
3. Comment **"I'll take this"** and follow the lines in the issue.

Frontend ideas: nicer chat UI, edit/reset buttons, drag-and-drop upload,
showing which file each answer came from. Backend ideas: better retrieval
(semantic search), support scanned PDFs, a `/api/delete` endpoint. Not a
coder? You can still file issues, test the chat on your own notices, and
improve the docs.

Stuck? Post in **Discussions** — no question is dumb.

## Layout

```text
app.py                  backend (endpoints, uploads, asks)
rag.py                  retrieval + answer logic
static/index.html       frontend - public chat page
static/admin.html       frontend - admin upload page
examples/               sample notice PDF to try
data/                   uploads + index (gitignored, created at runtime)
tests/                  tests (no installs beyond pytest-compatible unittest)
.env.example            template for your local, gitignored .env
```

## License

Code: [MIT](LICENSE).
"""app.py - run the chatbot web app.

    python app.py

then open http://127.0.0.1:5000 in your browser.

Pages:
  GET  /               the public chatbot page (open to everyone)
  GET  /admin          the admin page (upload + reset documents)

Endpoints:
  POST /api/upload     upload a notice PDF (ADMIN ONLY - X-Admin-Password header)
  GET  /api/files      list the files already uploaded (open)
  POST /api/reset      forget every uploaded document (ADMIN ONLY)
  POST /api/ask        ask a question (open to everyone; JSON: {"message": "..."})
"""

import hmac
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import rag

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB per file


def is_admin() -> bool:
    """The upload + reset endpoints are admin-only.

    The admin password lives in .env (ADMIN_PASSWORD). The frontend sends it
    in the 'X-Admin-Password' header. Asking questions needs NO admin access.
    """
    password = os.environ.get("ADMIN_PASSWORD", "") or ""
    provided = request.headers.get("X-Admin-Password", "") or ""
    return bool(password) and hmac.compare_digest(provided, password)


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/admin")
def admin():
    return send_from_directory(app.static_folder, "admin.html")


@app.post("/api/upload")
def upload():
    if not is_admin():
        return jsonify({"ok": False, "error": "admin password required"}), 401
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "no file selected"}), 400
    name = Path(file.filename).name  # keep only the file name (no folders)
    if not name.lower().endswith(".pdf"):
        return jsonify({"ok": False, "error": "only PDF files are supported"}), 400

    rag.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = rag.UPLOADS_DIR / name
    file.save(dest)
    try:
        chunks = rag.index_document(dest)
    except Exception as err:
        return jsonify({"ok": False, "error": str(err)}), 400
    return jsonify({"ok": True, "file": name, "chunks": chunks, "files": rag.list_sources()})


@app.get("/api/files")
def files():
    return jsonify({"files": rag.list_sources()})


@app.post("/api/reset")
def reset():
    if not is_admin():
        return jsonify({"ok": False, "error": "admin password required"}), 401
    rag.forget_all()
    return jsonify({"ok": True, "files": []})


@app.post("/api/ask")
def ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("message") or "").strip()
    if not question:
        return jsonify({"ok": False, "error": "empty question"}), 400
    try:
        answer, sources = rag.ask(question)
    except Exception as err:
        return jsonify({"ok": False, "error": str(err)}), 500
    return jsonify({"ok": True, "answer": answer, "sources": sources})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
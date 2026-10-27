# Uploading a notice — a plain-language walkthrough

This page explains how to put a notice (a PDF) into the app, step by step.
No technical knowledge is needed. If you can attach a file to an email, you can
do this.

There are two pages in the app, and they have different jobs:

| Page | Address | Who can use it |
|---|---|---|
| The chat page | `http://127.0.0.1:5000/` | Anyone. Ask questions here. |
| The admin page | `http://127.0.0.1:5000/admin` | Only people who know the admin password. Upload and delete happen here. |

So the short version is: **you upload on `/admin`, you ask questions on `/`.**
Nothing you type on the chat page can change or delete a document.

---

## Before you start

You need three things:

1. **The app is running.** Someone started it with `python app.py`, and the
   window it opened is still open. If that window was closed, the app is off.
2. **The admin password.** This is the value of `ADMIN_PASSWORD` in the `.env`
   file. It is not the same as any other password you own.
3. **A PDF file.** The notice itself. Paper notices that were scanned into a
   PDF are fine too — see the note about scanned files below.

---

## Step by step

### Step 1 — Open the admin page

In your browser, go to:

```
http://127.0.0.1:5000/admin
```

You will see a page with a password box and a place to choose a file.

### Step 2 — Type the admin password

Type the admin password into the password box.

Nothing is checked at this moment. The password is only sent when you actually
press the upload button, so a wrong password will not stop you from choosing a
file first.

### Step 3 — Choose your PDF

Press the button that says something like **Choose file** (the exact wording
depends on your browser) and pick the PDF from your computer.

If you pick something that is not a PDF — a Word document, a photo, a folder —
the app will refuse it and tell you so. Only `.pdf` files are accepted.

### Step 4 — Press Upload

Press **Upload**. Your browser will send two things to the app at the same
time: the file, and the password you typed.

### Step 5 — Wait, and watch the result message

Most notices finish in a second or two. You will see a message telling you how
many pieces the notice was split into, and the page will list the files that
are now loaded.

**But if your PDF is a scan, it takes longer.** A scanned PDF is a picture of a
page, not typed text. When the app notices it cannot read any text, it shows
each page to an AI model and asks the model to type the page out again. That
takes roughly **20 to 60 seconds per file**, and the app will appear to do
nothing while it works. Do not press Upload again — you would end up loading
the same notice twice.

### Step 6 — Go and ask a question

Open `http://127.0.0.1:5000/` and ask something the notice answers, for example:

> What time does the office open?

The reply will be based only on the notices you uploaded, and it will tell you
which file the answer came from.

---

## What the app does with your file

You do not need to know this to use the app, but it helps to understand why
some things behave the way they do.

1. The file is saved into a folder called `data/uploads/` on the same computer.
   It is not sent anywhere except to the AI model, and only the text of the
   notice is sent — never the whole file.
2. The notice's text is cut into small pieces (about 900 characters each, with
   a little overlap so a sentence that lands on a break is not lost).
3. Those pieces are saved in `data/index.json`.
4. When somebody asks a question, the app picks the few pieces whose words look
   most relevant, and gives only those pieces to the model to read.

Everything stays on the machine that runs the app. The `data/` folder is
deliberately kept out of version control, so uploaded notices are never
committed to the repository.

---

## When things go wrong

| What you see | What it means | What to do |
|---|---|---|
| "admin password required" | The password you typed does not match `ADMIN_PASSWORD`. | Check the `.env` file and type it again, exactly as written. |
| "no file selected" | You pressed Upload without choosing a file. | Choose a PDF first, then press Upload again. |
| "only PDF files are supported" | The file is not a PDF. | Export or save the notice as a PDF and try again. |
| The page shows a plain error, not a friendly message | The file is bigger than 10 MB, which is the limit the app allows. | Split the notice into smaller parts, or re-scan it at a lower quality. |
| Nothing seems to happen for a long time | Your PDF is a scan, and the app is having the pages read by the model. | Wait. Give it a full minute before worrying. |
| "could not read this PDF - the vision pass returned no usable text" | The app could not read the scan, usually because no AI key is set. | Check that `GEMINI_API_KEY` is filled in the `.env` file, then upload again. |
| The app answers "I could not find anything relevant..." | Nothing is uploaded yet, or the question does not match the notices. | Upload a notice first. Then ask using words that appear in it. |

### Two things worth knowing

- **Uploading the same file name twice** does not replace the old copy in the
  index. The second upload adds the notice's pieces a second time, so the same
  text may show up twice in answers. If you uploaded something by mistake, use
  **Reset** first, then upload the corrected file.
- **Reset forgets the index, not the files.** Pressing Reset makes the app
  answer from nothing again, but the PDFs themselves stay in
  `data/uploads/`. That is why a re-upload after a Reset can be useful: the
  old file is simply written over.

---

## Deleting everything

The admin page has a **Reset** button. It clears the list of pieces the app
knows about, so the chat page will say it has nothing to answer from. It needs
the same admin password as uploading.

If you want the PDFs gone from the disk as well, delete the files inside
`data/uploads/` and press Reset.

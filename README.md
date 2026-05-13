---
title: Abhishek Portfolio Chatbot
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: gradio
app_file: app.py
pinned: false
---

# Abhishek Raj — AI Portfolio Assistant

Live app:

- Hugging Face Space: https://darknightcoder-abhishek-ai-bot.hf.space
- GitHub Pages wrapper: https://abhishekraj1305.github.io/my_Ai_Chatbot/

## Aim

Build a free, local-first RAG chatbot that answers questions about Abhishek from documents stored in the `data/` folder. The app is designed for local use, Hugging Face Spaces deployment, and embedding inside a GitHub Pages portfolio.

## Features

- Loads PDF, DOCX, TXT, and Markdown files.
- Cleans text without stemming, lemmatization, stopword removal, or old NLP preprocessing.
- Splits documents into compact searchable chunks.
- Uses fast vectorless BM25-style retrieval by default.
- Avoids embedding downloads, Chroma startup, Torch, and Transformers on the live path.
- Uses Hugging Face Inference API only when explicitly enabled.
- Falls back to retrieval-based answers when no LLM is configured.
- Includes a free appointment request flow with Jitsi links.

## Tech Stack

- Python
- Gradio
- Vectorless in-memory retrieval
- pypdf
- python-docx

## Folder Structure

```text
chatbot/
├── app.py
├── ingest.py
├── rag_chain.py
├── document_loader.py
├── config.py
├── requirements.txt
├── README.md
├── .gitignore
├── data/
├── vector_db/
└── utils/
    ├── text_cleaner.py
    └── appointment.py
```

## Local Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open the local Gradio URL shown in the terminal.

## Add Documents

Place documents inside `data/`. Supported formats:

- `.pdf`
- `.docx`
- `.txt`
- `.md`

No ingestion step is required for the default vectorless mode. Restart the app
after adding or editing documents so it rebuilds the in-memory index.

## Run the Chatbot

```bash
python app.py
```

Suggested questions:

- Who is Abhishek?
- What skills does Abhishek have?
- What projects has Abhishek built?
- Can I book a call?
- What documents are you using?

## Hugging Face Llama Option

By default, the chatbot works without a remote LLM by using structured profile facts plus fast retrieval fallback. This is faster and more reliable for the embedded live widget. For richer generated answers, install `huggingface_hub`, then set these environment variables locally or as Hugging Face Space secrets:

```bash
ENABLE_HF_GENERATION=1
HF_TOKEN=your_hugging_face_token
HF_MODEL=meta-llama/Llama-3.1-8B-Instruct
```

Some Llama models require accepting the model license on Hugging Face before the token can use them.

## Hugging Face Spaces Deployment

1. Create a new Hugging Face Space.
2. Choose the Gradio SDK.
3. Upload this folder's files.
4. Make sure `app.py`, `requirements.txt`, `README.md`, and `data/` are included.
5. The Space will install dependencies from `requirements.txt`.
6. The app indexes documents in memory on first use; no vector database is required.

Optional Hugging Face generation:

1. Add `huggingface_hub` to `requirements.txt`.
2. Add Space secrets named `ENABLE_HF_GENERATION=1` and `HF_TOKEN`.
3. Optionally add `HF_MODEL` to choose a compatible text generation model.
4. Without this, the chatbot still works in fast retrieval fallback mode.

## Optional Chroma Backend

The old vector database path is still available for experimentation. To use it,
install `chromadb`, `langchain-text-splitters`, and `sentence-transformers`, set
`RETRIEVAL_BACKEND=chroma`, then run:

```bash
python ingest.py
```

Do not commit private documents or secrets to a public repository.

## GitHub Pages Embed

Use the direct Space URL format when possible:

```html
<iframe
  src="https://YOUR_USERNAME-YOUR_SPACE_NAME.hf.space"
  width="100%"
  height="700"
  style="border: none; border-radius: 16px;">
</iframe>
```

Alternative:

```html
<iframe
  src="https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME"
  width="100%"
  height="700"
  style="border: none; border-radius: 16px;">
</iframe>
```

## Appointment MVP

The chatbot detects appointment intent such as "book call", "appointment", "schedule", "meeting", and "call with Abhishek". It asks for:

- Name
- Email
- Preferred date
- Preferred time and timezone
- Purpose of call

It checks local booked slots in `data/bookings.json`, suggests available slots for the requested date, prevents duplicate bookings for the same time, and generates a free Jitsi meeting link.

Jitsi is only the video meeting room. It does not work like a scheduler, so it will not show the chatbot's requested meeting time. The chatbot stores the actual schedule in `data/bookings.json`, shows it in the protected **Admin bookings** panel, and can send email alerts when SMTP is configured.

Optional notification and calendar environment variables:

```bash
ADMIN_PIN=choose_a_private_admin_pin
OWNER_EMAIL=r.abhishek1305@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
GOOGLE_CALENDAR_ID=your_calendar_id
BOOKING_TIMEZONE=Asia/Kolkata
BOOKING_DURATION_MINUTES=30
```

If email is not configured, booking notifications are written to `data/booking_notifications.log`. On Hugging Face Spaces, SMTP may be blocked, so the app skips slow SMTP attempts there unless `EMAIL_WEBHOOK_URL` or `RESEND_API_KEY` is configured. If Google Calendar credentials are not configured, the app still prevents double booking locally.

For Gmail SMTP, create a Gmail App Password and use that as `SMTP_PASSWORD`; do not use your normal Gmail password.

## Future Improvements

- Google Calendar integration.
- Gmail confirmation emails.
- Better local or hosted LLM.
- Conversation analytics.
- Authentication or admin panel.
- Contact form integration.
- Stronger source citations with page-level display in the UI.

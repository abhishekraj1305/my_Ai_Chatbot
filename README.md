---
title: Abhishek Portfolio Chatbot
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: latest
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
- Splits documents into semantic chunks.
- Embeds chunks with `sentence-transformers/all-MiniLM-L6-v2`.
- Stores vectors in persistent ChromaDB.
- Retrieves top matching portfolio context.
- Uses Hugging Face Inference API only when `HF_TOKEN` is available.
- Falls back to retrieval-based answers when no LLM is configured.
- Includes a free appointment request flow with Jitsi links.

## Tech Stack

- Python
- Gradio
- ChromaDB
- LangChain text splitter
- Sentence Transformers
- pypdf
- python-docx
- Hugging Face Hub

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
python ingest.py
python app.py
```

Then open the local Gradio URL shown in the terminal.

## Add Documents

Place documents inside `data/`. Supported formats:

- `.pdf`
- `.docx`
- `.txt`
- `.md`

Run ingestion again after adding or editing documents:

```bash
python ingest.py
```

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

By default, the chatbot works without an LLM by using structured profile facts plus retrieval fallback. For better natural answers, set these environment variables locally or as Hugging Face Space secrets:

```bash
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
6. On first query, if `vector_db/` is missing, the app attempts to ingest the `data/` folder automatically.

Optional Hugging Face generation:

1. Add a Space secret named `HF_TOKEN`.
2. Optionally add `HF_MODEL` to choose a compatible text generation model.
3. Without `HF_TOKEN`, the chatbot still works in retrieval fallback mode.

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

If SMTP is not configured, booking notifications are written to `data/booking_notifications.log`. If Google Calendar credentials are not configured, the app still prevents double booking locally.

For Gmail SMTP, create a Gmail App Password and use that as `SMTP_PASSWORD`; do not use your normal Gmail password.

## Future Improvements

- Google Calendar integration.
- Gmail confirmation emails.
- Better local or hosted LLM.
- Conversation analytics.
- Authentication or admin panel.
- Contact form integration.
- Stronger source citations with page-level display in the UI.

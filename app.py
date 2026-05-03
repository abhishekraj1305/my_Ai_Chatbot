"""Gradio entry point for Abhishek's AI Portfolio Assistant."""

from __future__ import annotations

import html
import os
import re

import gradio as gr

from rag_chain import answer_question
from utils.appointment import (
    is_appointment_intent,
    start_booking_state,
    update_booking_state,
)
from utils.booking_backend import BOOKINGS_PATH, list_bookings


TITLE = "Abhishek's AI Bot"
DESCRIPTION = "Ask about Abhishek's work, projects, book, services, or book a call."

SUGGESTED_QUESTIONS = [
    "Who is Abhishek?",
    "What projects has Abhishek built?",
    "What are Abhishek's Python skills?",
    "What services does Abhishek offer?",
    "Can I book a call with Abhishek?",
]


def chat(message: str, history: list[dict]) -> str:
    result = answer_question(message)
    return result["answer"]


def _format_markdown_light(text: str) -> str:
    escaped = html.escape(text or "")
    escaped = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", escaped)
    lines = escaped.splitlines()
    output = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                output.append("</ul>")
                in_list = False
            continue
        if stripped.startswith("- "):
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{stripped[2:]}</li>")
        else:
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append(f"<p>{stripped}</p>")

    if in_list:
        output.append("</ul>")

    return "\n".join(output)


def render_history(history: list[dict] | None) -> str:
    history = history or []
    if not history:
        return (
            "<div class='conversation'>"
            "<article class='msg-row assistant'>"
            "<div class='msg-avatar'>AI</div>"
            "<div class='msg-body'>"
            "<div class='msg-bubble greeting'>Hi! I am Abhishek's AI Bot. How can I help you?</div>"
            "</div></article></div>"
        )

    messages = []
    for item in history:
        role = item.get("role", "assistant")
        label = "You" if role == "user" else "Abhishek AI"
        content = _format_markdown_light(item.get("content", ""))
        messages.append(
            f"""
            <article class="msg-row {role}">
              <div class="msg-avatar">{'Y' if role == 'user' else 'AI'}</div>
              <div class="msg-body">
                <div class="msg-label">{label}</div>
                <div class="msg-bubble">{content}</div>
              </div>
            </article>
            """
        )

    return "<div class='conversation'>" + "\n".join(messages) + "</div>"


def respond(
    message: str, history: list[dict], booking_state: dict | None
) -> tuple[str, list[dict], str, dict | None]:
    message = (message or "").strip()
    if not message:
        return "", history, render_history(history), booking_state

    if booking_state and booking_state.get("active"):
        answer, booking_state = update_booking_state(message, booking_state)
    elif is_appointment_intent(message):
        booking_state = start_booking_state()
        answer = "Sure. Please share your name."
    else:
        answer = chat(message, history)

    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ]
    return "", history, render_history(history), booking_state


def use_example(
    question: str, history: list[dict], booking_state: dict | None
) -> tuple[str, list[dict], str, dict | None]:
    return respond(question, history, booking_state)


def clear_chat() -> tuple[list[dict], str, dict | None]:
    return [], render_history([]), None


def render_admin_bookings(pin: str) -> str:
    expected_pin = os.getenv("ADMIN_PIN")
    if not expected_pin:
        return (
            "<div class='admin-card'>"
            "<h3>Admin booking alerts are local right now</h3>"
            "<p>Set <code>ADMIN_PIN</code> in <code>.env</code> to enable this protected dashboard.</p>"
            f"<p>Until email is configured, booking alerts are saved in <code>{html.escape(str(BOOKINGS_PATH))}</code> and "
            f"<code>{html.escape(str(BOOKINGS_PATH.parent / 'booking_notifications.log'))}</code>.</p>"
            "</div>"
        )
    if (pin or "").strip() != expected_pin:
        return (
            "<div class='admin-card'>"
            "<h3>Admin dashboard locked</h3>"
            "<p>Enter your admin PIN and click refresh to view booking requests.</p>"
            "</div>"
        )

    bookings = list_bookings()
    if not bookings:
        return (
            "<div class='admin-card'>"
            "<h3>No bookings yet</h3>"
            "<p>When someone books a call, it will appear here with the slot, purpose, and Jitsi link.</p>"
            "</div>"
        )

    rows = []
    for booking in bookings:
        meeting_link = html.escape(booking.get("meeting_link", ""))
        rows.append(
            "<tr>"
            f"<td>{html.escape(booking.get('slot_label', '-'))}</td>"
            f"<td>{html.escape(booking.get('name', '-'))}</td>"
            f"<td>{html.escape(booking.get('email', '-'))}</td>"
            f"<td>{html.escape(booking.get('purpose', '-'))}</td>"
            f"<td><a href='{meeting_link}' target='_blank' rel='noreferrer'>Join</a></td>"
            f"<td>{html.escape(booking.get('status', 'requested'))}</td>"
            "</tr>"
        )

    return (
        "<div class='admin-card'>"
        "<h3>Booking requests</h3>"
        "<p>These are the chatbot bookings, sorted by meeting time. Jitsi itself will not show this schedule.</p>"
        "<table class='admin-table'>"
        "<thead><tr><th>Slot</th><th>Name</th><th>Email</th><th>Purpose</th><th>Meet</th><th>Status</th></tr></thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


with gr.Blocks(title=TITLE) as demo:
    with gr.Column(elem_id="chat-shell"):
        gr.Markdown(
            f"""
            <div class="hero">
              <h1>{TITLE}</h1>
              <p>{DESCRIPTION}</p>
            </div>
            """
        )

        history_state = gr.State([])
        booking_state = gr.State(None)
        conversation = gr.HTML(render_history([]), elem_id="conversation-window")

        with gr.Accordion("Suggested questions", open=False, elem_id="suggestions-panel"):
            with gr.Row(elem_id="suggestions"):
                example_buttons = [
                    gr.Button(question, elem_classes=["suggestion-chip"])
                    for question in SUGGESTED_QUESTIONS
                ]

        with gr.Row(elem_id="composer-row"):
            textbox = gr.Textbox(
                placeholder="Type your message here...",
                label="",
                show_label=False,
                container=False,
                lines=1,
                max_lines=4,
                scale=9,
                min_width=0,
                elem_id="composer",
            )
            send = gr.Button("Send", scale=1, min_width=82, elem_id="send-button")

        with gr.Accordion("Admin bookings", open=False, elem_id="admin-panel"):
            with gr.Row(elem_id="admin-controls"):
                admin_pin = gr.Textbox(
                    placeholder="Admin PIN",
                    label="",
                    show_label=False,
                    type="password",
                    container=False,
                    elem_id="admin-pin",
                )
                refresh_admin = gr.Button("Refresh", elem_id="admin-refresh")
            admin_bookings = gr.HTML(render_admin_bookings(""), elem_id="admin-bookings")

        textbox.submit(
            respond,
            [textbox, history_state, booking_state],
            [textbox, history_state, conversation, booking_state],
        )
        send.click(
            respond,
            [textbox, history_state, booking_state],
            [textbox, history_state, conversation, booking_state],
        )
        for button, question in zip(example_buttons, SUGGESTED_QUESTIONS):
            button.click(
                use_example,
                inputs=[gr.State(question), history_state, booking_state],
                outputs=[textbox, history_state, conversation, booking_state],
            )
        refresh_admin.click(render_admin_bookings, inputs=[admin_pin], outputs=[admin_bookings])


if __name__ == "__main__":
    is_space = bool(os.getenv("SPACE_ID") or os.getenv("SPACE_HOST"))
    demo.launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0" if is_space else "127.0.0.1"),
        server_port=int(os.getenv("PORT", os.getenv("GRADIO_SERVER_PORT", "7860"))),
        theme=gr.themes.Soft(primary_hue="purple", secondary_hue="violet"),
        css="""
        :root {
          --bg: #f8f5ff;
          --header: #8a2be2;
          --panel: #ffffff;
          --panel-soft: #ffffff;
          --bot: #f1f3f8;
          --user: #a855f7;
          --text: #111827;
          --muted: #746b86;
          --line: rgba(168, 85, 247, 0.28);
          --accent: #a855f7;
          --accent-strong: #7e22ce;
          --accent-glow: rgba(217, 70, 239, 0.34);
        }
        * {
          box-sizing: border-box !important;
        }
        html,
        body {
          height: 100% !important;
          overflow: hidden !important;
        }
        body, .gradio-container {
          background: var(--bg) !important;
          color: var(--text) !important;
          font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
        }
        main,
        .main,
        .contain {
          height: 100vh !important;
          overflow: hidden !important;
        }
        .gradio-container {
          max-width: 720px !important;
          margin: auto !important;
          padding: 0 14px 12px !important;
          height: 100dvh !important;
          overflow: hidden !important;
          overflow-x: hidden !important;
        }
        .html-container,
        .html-container > *,
        #conversation-window,
        #conversation-window *,
        #chat-shell,
        #chat-shell > * {
          max-width: 100% !important;
          overflow-x: hidden !important;
        }
        #chat-shell {
          height: 100dvh;
          gap: 10px;
          display: flex !important;
          flex-direction: column !important;
          overflow: hidden !important;
          overflow-x: hidden !important;
        }
        .hero {
          background: linear-gradient(135deg, #7c3aed 0%, #a855f7 48%, #d946ef 100%);
          margin: 0 -14px 0;
          padding: 16px 20px 14px;
          color: white;
          overflow: hidden;
          box-shadow: 0 0 28px var(--accent-glow);
        }
        .hero h1 {
          margin: 0;
          font-size: 1.36rem;
          line-height: 1.15;
          letter-spacing: 0;
          color: white;
          white-space: normal;
        }
        .hero p {
          margin: 6px 0 0;
          color: rgba(255, 255, 255, 0.9);
          font-size: 0.84rem;
        }
        #conversation-window {
          border: none !important;
          border-radius: 0 !important;
          background: var(--panel) !important;
          box-shadow: none;
          flex: 1 1 auto !important;
          height: calc(100dvh - 390px) !important;
          max-height: calc(100dvh - 390px) !important;
          min-height: 0 !important;
          overflow-y: auto !important;
          overflow-x: hidden !important;
          padding: 22px 16px 18px;
        }
        #conversation-window > div,
        #conversation-window .html-container,
        #conversation-window .prose {
          height: 100% !important;
          max-height: 100% !important;
          overflow-y: auto !important;
          overflow-x: hidden !important;
        }
        .conversation {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .msg-row {
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          gap: 6px;
          align-items: start;
        }
        .msg-row.user {
          max-width: 82%;
          margin-left: auto;
        }
        .msg-avatar {
          display: none;
        }
        .msg-label {
          display: none;
        }
        .msg-bubble {
          width: fit-content;
          max-width: min(88%, 560px);
          background: var(--bot);
          color: var(--text);
          border: none;
          border-radius: 18px;
          padding: 12px 16px;
          line-height: 1.48;
          font-size: 1rem;
        }
        .msg-bubble,
        .msg-bubble *,
        #conversation-window p,
        #conversation-window li {
          color: #eef2ff !important;
        }
        .msg-row.assistant .msg-bubble,
        .msg-row.assistant .msg-bubble *,
        #conversation-window .msg-row.assistant p,
        #conversation-window .msg-row.assistant li {
          color: var(--text) !important;
        }
        .msg-row.user .msg-bubble {
          background: linear-gradient(135deg, #9333ea 0%, #c026d3 100%);
          box-shadow: 0 0 18px var(--accent-glow);
          color: white;
          margin-left: auto;
        }
        .msg-row.user .msg-bubble,
        .msg-row.user .msg-bubble * {
          color: #ffffff !important;
        }
        .msg-row.assistant .msg-bubble {
          border-top-left-radius: 6px;
        }
        .msg-bubble p {
          margin: 0 0 10px;
        }
        .msg-bubble p:last-child {
          margin-bottom: 0;
        }
        .msg-bubble ul {
          margin: 6px 0 0 18px;
          padding: 0;
        }
        .msg-bubble li {
          margin: 6px 0;
        }
        #composer-row {
          align-items: stretch;
          gap: 8px;
          background: transparent !important;
          flex: 0 0 auto !important;
          z-index: 3;
          flex-wrap: nowrap !important;
          min-width: 0 !important;
          width: 100% !important;
        }
        #suggestions-panel {
          border: 1px solid var(--line) !important;
          border-radius: 15px !important;
          background: white !important;
          flex: 0 0 auto !important;
          box-shadow: 0 8px 20px rgba(88, 28, 135, 0.07) !important;
        }
        #admin-panel {
          border: 1px solid var(--line) !important;
          border-radius: 15px !important;
          background: white !important;
          flex: 0 0 auto !important;
        }
        #admin-controls {
          gap: 8px;
          align-items: stretch;
        }
        #admin-pin,
        #admin-pin input {
          min-height: 42px !important;
          border-radius: 14px !important;
          border: 1px solid var(--line) !important;
        }
        #admin-refresh {
          border-radius: 14px !important;
          background: var(--accent-strong) !important;
          color: white !important;
          border: none !important;
        }
        .admin-card {
          background: #fbf8ff;
          border: 1px solid var(--line);
          border-radius: 14px;
          padding: 14px;
          color: var(--text);
          overflow-x: auto;
        }
        .admin-card h3 {
          margin: 0 0 8px;
          font-size: 1rem;
        }
        .admin-card p {
          margin: 0 0 8px;
          color: var(--muted);
          line-height: 1.45;
        }
        .admin-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.86rem;
        }
        .admin-table th,
        .admin-table td {
          border-bottom: 1px solid rgba(168, 85, 247, 0.16);
          padding: 8px 6px;
          text-align: left;
          vertical-align: top;
        }
        .admin-table th {
          color: #581c87;
          font-weight: 800;
        }
        .admin-table a {
          color: var(--accent-strong);
          font-weight: 800;
        }
        #suggestions-panel summary,
        #suggestions-panel .label-wrap,
        #admin-panel summary,
        #admin-panel .label-wrap {
          color: var(--muted) !important;
          font-weight: 700 !important;
        }
        #composer,
        #composer textarea {
          min-height: 54px !important;
          border-radius: 18px !important;
          background: var(--panel-soft) !important;
          color: var(--text) !important;
          border: 2px solid var(--accent) !important;
          box-shadow: 0 0 0 2px rgba(168, 85, 247, 0.08), 0 0 18px rgba(168, 85, 247, 0.18) !important;
        }
        #composer textarea {
          padding: 14px 16px !important;
          resize: vertical !important;
        }
        #composer textarea::placeholder {
          color: #7f8aa0 !important;
        }
        #send-button,
        #clear-button {
          border-radius: 18px !important;
          min-height: 54px !important;
          font-weight: 700 !important;
        }
        #send-button {
          background: var(--accent) !important;
          color: white !important;
          border: none !important;
          min-width: 92px !important;
          max-width: 96px !important;
          box-shadow: 0 0 18px var(--accent-glow) !important;
        }
        #clear-button {
          background: #e9eee2 !important;
          color: var(--text) !important;
          border: 1px solid var(--line) !important;
        }
        #suggestions {
          gap: 10px;
          flex-wrap: wrap;
        }
        .suggestion-chip {
          border-radius: 999px !important;
          background: #faf7ff !important;
          color: var(--text) !important;
          border: 1px solid var(--line) !important;
          min-height: 40px !important;
          font-size: 0.9rem !important;
          font-weight: 650 !important;
          padding: 0 14px !important;
        }
        .suggestion-chip:hover {
          background: #efe7ff !important;
          border-color: rgba(168, 85, 247, 0.65) !important;
        }
        @media (max-width: 520px) {
          .gradio-container {
            padding: 0 10px 10px !important;
          }
          .hero {
            margin: 0 -10px 0;
            padding: 14px 14px 12px;
          }
          .hero h1 {
            font-size: 1.22rem;
          }
          .hero p {
            font-size: 0.78rem;
          }
          #conversation-window {
            height: calc(100dvh - 350px) !important;
            max-height: calc(100dvh - 350px) !important;
            padding: 18px 10px 14px;
          }
          .msg-row.user {
            max-width: 86%;
          }
          .msg-bubble {
            max-width: 94%;
            font-size: 0.95rem;
          }
          #send-button {
            min-width: 84px !important;
            max-width: 88px !important;
          }
        }
        .block-label {
          display: none !important;
        }
        footer { display: none !important; }
        """,
    )

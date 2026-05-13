"""Gradio entry point for Abhishek's AI Portfolio Assistant."""

from __future__ import annotations

import html
import os
import re
from typing import Any

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

MINI_BOT_HTML = """
<div class="mini-bot-row" aria-hidden="true">
  <div id="mini-bot">
    <div class="bot-speech"><span>Hi!</span><span>Ask me</span><span>Bye!</span></div>
    <div class="bot-emoji">🤖</div>
    <div class="bot-shadow"></div>
  </div>
</div>
"""

CHAT_BOTTOM_SCRIPT = """
<script>
(() => {
  const run = () => {
    const root = document.querySelector("#conversation-window");
    if (!root) return;
    const bottom = root.querySelector("#chat-bottom");
    [
      document.scrollingElement,
      ...document.querySelectorAll("body, main, .main, .contain, .gradio-container, #chat-shell, #conversation-window, #conversation-window .html-container, #conversation-window .prose, #conversation-window .conversation")
    ].forEach((node) => {
      if (node) node.scrollTop = node.scrollHeight;
    });
    if (bottom) {
      bottom.scrollIntoView({ block: "end", inline: "nearest" });
    }
  };
  requestAnimationFrame(run);
  setTimeout(run, 80);
  setTimeout(run, 240);
  setTimeout(run, 700);
  setTimeout(run, 1400);
})();
</script>
"""


CHAT_SCROLL_JS = """
() => {
  let lastMessageCount = 0;

  const scrollTargets = () => {
    const root = document.querySelector("#conversation-window");
    if (!root) return [];

    return [
      document.scrollingElement,
      ...document.querySelectorAll("body, main, .main, .contain, .gradio-container, #chat-shell, #conversation-window, #conversation-window .html-container, #conversation-window .prose, #conversation-window .conversation")
    ].filter((node, index, nodes) => node && nodes.indexOf(node) === index);
  };

  const scrollToLatest = () => {
    const root = document.querySelector("#conversation-window");
    if (!root) return;
    const bottom = root.querySelector("#chat-bottom");

    const run = () => {
      scrollTargets().forEach((node) => {
        node.scrollTop = node.scrollHeight;
      });
      root.scrollTop = root.scrollHeight;
      if (bottom) {
        bottom.scrollIntoView({ block: "end", inline: "nearest" });
      }
    };

    requestAnimationFrame(run);
    setTimeout(run, 80);
    setTimeout(run, 240);
    setTimeout(run, 700);
    setTimeout(run, 1400);
  };

  const syncIfNewMessage = () => {
    const count = document.querySelectorAll("#conversation-window .msg-row").length;
    if (count !== lastMessageCount) {
      lastMessageCount = count;
      scrollToLatest();
    }
  };

  const attachObserver = () => {
    const root = document.querySelector("#conversation-window");
    if (!root || root.dataset.scrollObserverAttached === "true") return;
    const observer = new MutationObserver(scrollToLatest);
    observer.observe(root, { childList: true, subtree: true, characterData: true });
    root.dataset.scrollObserverAttached = "true";
    lastMessageCount = root.querySelectorAll(".msg-row").length;
    scrollToLatest();
  };

  document.addEventListener("click", (event) => {
    if (event.target.closest("#send-button, #suggestions-panel button")) {
      setTimeout(scrollToLatest, 120);
      setTimeout(scrollToLatest, 500);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.closest("#composer")) {
      setTimeout(scrollToLatest, 120);
      setTimeout(scrollToLatest, 500);
    }
  });

  attachObserver();
  setInterval(attachObserver, 500);
  setInterval(syncIfNewMessage, 250);
}
"""

SCROLL_AFTER_RESPONSE_JS = """
() => {
  const run = () => {
    const root = document.querySelector("#conversation-window");
    if (!root) return;
    const bottom = root.querySelector("#chat-bottom");
    [
      document.scrollingElement,
      ...document.querySelectorAll("body, main, .main, .contain, .gradio-container, #chat-shell, #conversation-window, #conversation-window .html-container, #conversation-window .prose, #conversation-window .conversation")
    ].forEach((node) => {
      if (node) node.scrollTop = node.scrollHeight;
    });
    if (bottom) {
      bottom.scrollIntoView({ block: "end", inline: "nearest" });
    }
  };
  requestAnimationFrame(run);
  setTimeout(run, 80);
  setTimeout(run, 220);
  setTimeout(run, 650);
  setTimeout(run, 1200);
}
"""


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
            f"</div></article>{MINI_BOT_HTML}<div id='chat-bottom'></div></div>{CHAT_BOTTOM_SCRIPT}"
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

    return (
        "<div class='conversation'>"
        + "\n".join(messages)
        + MINI_BOT_HTML
        + "<div id='chat-bottom'></div></div>"
        + CHAT_BOTTOM_SCRIPT
    )


def respond(
    message: str, history: list[dict], booking_state: dict | None
) -> tuple[str, list[dict], str, dict | None, Any]:
    message = (message or "").strip()
    if not message:
        return "", history, render_history(history), booking_state, gr.update()

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
    return "", history, render_history(history), booking_state, gr.update(visible=False)


def use_example(
    question: str, history: list[dict], booking_state: dict | None
) -> tuple[str, list[dict], str, dict | None, Any]:
    if booking_state and booking_state.get("active") and not is_appointment_intent(question):
        booking_state = None
    return respond(question, history, booking_state)


def clear_chat() -> tuple[list[dict], str, dict | None, Any]:
    return [], render_history([]), None, gr.update(visible=True)


def noop() -> None:
    return None


def render_admin_bookings(pin: str) -> str:
    expected_pin = os.getenv("ADMIN_PIN")
    if not expected_pin:
        return (
            "<div class='admin-card'>"
            "<h3>Admin booking portal</h3>"
            "<p>Set <code>ADMIN_PIN</code> in <code>.env</code> to enable this protected dashboard.</p>"
            f"<p>Until email is configured, booking alerts are saved in <code>{html.escape(str(BOOKINGS_PATH))}</code> and "
            f"<code>{html.escape(str(BOOKINGS_PATH.parent / 'booking_notifications.log'))}</code>.</p>"
            "</div>"
        )
    if (pin or "").strip() != expected_pin:
        return (
            "<div class='admin-card'>"
            "<h3>Admin booking portal locked</h3>"
            "<p>Enter the PIN from <code>ADMIN_PIN</code> in your runtime environment, then click unlock.</p>"
            "</div>"
        )

    bookings = list_bookings()
    if not bookings:
        return (
            "<div class='admin-card'>"
            "<h3>No bookings yet</h3>"
            "<p>When someone books a call, it will appear here with the slot, visitor email, purpose, Jitsi link, and email status.</p>"
            "</div>"
        )

    cards = []
    for booking in reversed(bookings):
        meeting_link = html.escape(booking.get("meeting_link", ""))
        notifications = booking.get("notifications") or {}
        owner_sent = notifications.get("owner_email_sent")
        visitor_sent = notifications.get("visitor_email_sent")
        errors = booking.get("notification_errors") or notifications.get("errors") or []
        if owner_sent and visitor_sent:
            mail_status = "Owner + visitor sent"
        elif owner_sent:
            mail_status = "Owner sent"
        elif notifications.get("smtp_configured"):
            mail_status = "Email failed"
        else:
            mail_status = "SMTP missing"
        error_text = "; ".join(str(error) for error in errors)
        cards.append(
            "<article class='booking-card'>"
            "<div class='booking-card-top'>"
            f"<strong>{html.escape(booking.get('slot_label', '-'))}</strong>"
            f"<span>{html.escape(booking.get('status', 'requested'))}</span>"
            "</div>"
            f"<p><b>Name</b>{html.escape(booking.get('name', '-'))}</p>"
            f"<p><b>Email</b>{html.escape(booking.get('email', '-'))}</p>"
            f"<p><b>Purpose</b>{html.escape(booking.get('purpose', '-'))}</p>"
            "<div class='booking-card-actions'>"
            f"<a href='{meeting_link}' target='_blank' rel='noreferrer'>Open meeting</a>"
            f"<span class='mail-status'>{html.escape(mail_status)}</span>"
            "</div>"
            f"{'<small>' + html.escape(error_text) + '</small>' if error_text else ''}"
            "</article>"
        )

    return (
        "<div class='admin-card'>"
        "<h3>All bookings</h3>"
        "<p>Latest requests are shown first. Open the meeting link directly from each card.</p>"
        "<div class='booking-card-list'>"
        + "".join(cards)
        + "</div></div>"
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
        with gr.Column(elem_id="suggestions-panel") as suggestions_panel:
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
                refresh_admin = gr.Button("Unlock / Refresh", elem_id="admin-refresh")
            admin_bookings = gr.HTML(render_admin_bookings(""), elem_id="admin-bookings")

        textbox_submit_event = textbox.submit(
            respond,
            [textbox, history_state, booking_state],
            [textbox, history_state, conversation, booking_state, suggestions_panel],
        )
        textbox_submit_event.then(
            fn=noop,
            inputs=None,
            outputs=None,
            js=SCROLL_AFTER_RESPONSE_JS,
            queue=False,
            show_progress="hidden",
        )
        send_click_event = send.click(
            respond,
            [textbox, history_state, booking_state],
            [textbox, history_state, conversation, booking_state, suggestions_panel],
        )
        send_click_event.then(
            fn=noop,
            inputs=None,
            outputs=None,
            js=SCROLL_AFTER_RESPONSE_JS,
            queue=False,
            show_progress="hidden",
        )
        for button, question in zip(example_buttons, SUGGESTED_QUESTIONS):
            example_click_event = button.click(
                use_example,
                inputs=[gr.State(question), history_state, booking_state],
                outputs=[textbox, history_state, conversation, booking_state, suggestions_panel],
            )
            example_click_event.then(
                fn=noop,
                inputs=None,
                outputs=None,
                js=SCROLL_AFTER_RESPONSE_JS,
                queue=False,
                show_progress="hidden",
            )
        admin_refresh_event = refresh_admin.click(
            render_admin_bookings, inputs=[admin_pin], outputs=[admin_bookings]
        )
        admin_refresh_event.then(
            fn=noop,
            inputs=None,
            outputs=None,
            js="() => setTimeout(() => document.querySelector('#admin-bookings')?.scrollIntoView({block: 'nearest'}), 80)",
            queue=False,
            show_progress="hidden",
        )
        admin_pin.submit(render_admin_bookings, inputs=[admin_pin], outputs=[admin_bookings])


if __name__ == "__main__":
    is_space = bool(os.getenv("SPACE_ID") or os.getenv("SPACE_HOST"))
    demo.launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0" if is_space else "127.0.0.1"),
        server_port=int(os.getenv("PORT", os.getenv("GRADIO_SERVER_PORT", "7860"))),
        js=CHAT_SCROLL_JS,
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
          overflow-y: auto !important;
          overflow-x: hidden !important;
        }
        .gradio-container {
          max-width: 780px !important;
          margin: auto !important;
          padding: 0 8px 8px !important;
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
          gap: 7px;
          display: flex !important;
          flex-direction: column !important;
          overflow: hidden !important;
          overflow-x: hidden !important;
          position: relative !important;
        }
        .hero {
          background: linear-gradient(135deg, #7c3aed 0%, #a855f7 48%, #d946ef 100%);
          margin: 0 -8px 0;
          padding: 12px 16px 10px;
          color: white;
          overflow: hidden;
          box-shadow: 0 0 28px var(--accent-glow);
          flex: 0 0 auto !important;
        }
        .hero h1 {
          margin: 0;
          font-size: 1.26rem;
          line-height: 1.15;
          letter-spacing: 0;
          color: white;
          white-space: normal;
        }
        .hero p {
          margin: 4px 0 0;
          color: rgba(255, 255, 255, 0.9);
          font-size: 0.82rem;
        }
        #conversation-window {
          border: none !important;
          border-radius: 0 !important;
          background: var(--panel) !important;
          box-shadow: none;
          flex: 0 1 auto !important;
          height: clamp(220px, calc(100dvh - 405px), 520px) !important;
          max-height: clamp(220px, calc(100dvh - 405px), 520px) !important;
          min-height: 180px !important;
          overflow-y: auto !important;
          overflow-x: hidden !important;
          padding: 18px 26px 14px;
          overscroll-behavior: contain !important;
          scroll-behavior: smooth !important;
          position: relative;
        }
        #conversation-window > div,
        #conversation-window .html-container,
        #conversation-window .prose {
          height: auto !important;
          max-height: none !important;
          min-height: 100% !important;
          overflow-y: visible !important;
          overflow-x: hidden !important;
        }
        .conversation {
          display: flex;
          flex-direction: column;
          gap: 14px;
          min-height: 100%;
          padding-bottom: 2px;
          position: relative;
          z-index: 1;
        }
        .mini-bot-row {
          display: flex;
          justify-content: flex-end;
          min-height: 104px;
          margin-top: -2px;
          padding-right: 8px;
          pointer-events: none;
        }
        #mini-bot {
          position: relative;
          width: 92px;
          height: 88px;
          pointer-events: none;
          z-index: 3;
          overflow: visible;
        }
        .bot-emoji {
          width: 56px;
          height: 56px;
          margin: 18px 0 0 auto;
          border-radius: 19px;
          display: grid;
          place-items: center;
          background: linear-gradient(135deg, rgba(124, 58, 237, 0.95), rgba(217, 70, 239, 0.95));
          box-shadow: 0 14px 28px rgba(126, 34, 206, 0.22);
          font-size: 1.92rem;
          line-height: 1;
          transform-origin: 50% 100%;
          animation: bot-hop 3.4s ease-in-out infinite;
        }
        .bot-emoji::before {
          content: "";
          position: absolute;
        }
        .bot-face {
          width: 42px;
          height: 34px;
          margin: 0 auto;
          border-radius: 16px 16px 14px 14px;
          background: linear-gradient(135deg, #7c3aed, #d946ef);
          box-shadow: 0 10px 24px rgba(126, 34, 206, 0.28);
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }
        .bot-face::before {
          content: "";
          position: absolute;
          inset: 4px;
          border-radius: 13px;
          border: 1px solid rgba(255, 255, 255, 0.25);
        }
        .bot-eye {
          width: 6px;
          height: 8px;
          border-radius: 999px;
          background: #ffffff;
          animation: bot-blink 4s infinite;
        }
        .bot-mouth {
          position: absolute;
          left: 16px;
          bottom: 7px;
          width: 10px;
          height: 4px;
          border-radius: 0 0 999px 999px;
          border-bottom: 2px solid rgba(255, 255, 255, 0.92);
        }
        .bot-body {
          width: 34px;
          height: 24px;
          margin: -2px auto 0;
          border-radius: 10px 10px 14px 14px;
          background: linear-gradient(135deg, rgba(168, 85, 247, 0.95), rgba(34, 211, 238, 0.9));
          box-shadow: 0 8px 18px rgba(34, 211, 238, 0.18);
        }
        .bot-body::before,
        .bot-body::after {
          content: "";
          position: absolute;
          width: 10px;
          height: 3px;
          border-radius: 999px;
          background: #a855f7;
          bottom: 21px;
        }
        .bot-body::before {
          left: 7px;
          transform: rotate(24deg);
        }
        .bot-body::after {
          right: 7px;
          transform: rotate(-24deg);
        }
        .bot-antenna {
          width: 2px;
          height: 11px;
          margin: 0 auto -1px;
          background: #7c3aed;
          position: relative;
        }
        .bot-antenna::before {
          content: "";
          position: absolute;
          left: 50%;
          top: -6px;
          width: 8px;
          height: 8px;
          border-radius: 999px;
          transform: translateX(-50%);
          background: #22d3ee;
          box-shadow: 0 0 14px rgba(34, 211, 238, 0.9);
        }
        .bot-shadow {
          width: 34px;
          height: 8px;
          margin: 4px auto 0;
          border-radius: 999px;
          background: rgba(88, 28, 135, 0.16);
          animation: bot-shadow 6.5s ease-in-out infinite;
        }
        .bot-speech {
          position: absolute;
          right: 42px;
          top: 5px;
          min-width: 58px;
          padding: 5px 8px;
          border-radius: 12px 12px 4px 12px;
          background: rgba(255, 255, 255, 0.86);
          border: 1px solid rgba(168, 85, 247, 0.26);
          color: #581c87;
          font-size: 0.72rem;
          font-weight: 850;
          box-shadow: 0 8px 18px rgba(88, 28, 135, 0.12);
          height: 26px;
          overflow: hidden;
        }
        .bot-speech span {
          position: absolute;
          left: 8px;
          right: 8px;
          opacity: 0;
          white-space: nowrap;
        }
        .bot-speech span:nth-child(1) {
          animation: bot-say-one 6.5s linear infinite;
        }
        .bot-speech span:nth-child(2) {
          animation: bot-say-two 6.5s linear infinite;
        }
        .bot-speech span:nth-child(3) {
          animation: bot-say-three 6.5s linear infinite;
        }
        @keyframes bot-hop {
          0%, 100% {
            transform: translate3d(0, 0, 0) rotate(-2deg);
          }
          22% {
            transform: translate3d(-18px, -16px, 0) rotate(6deg);
          }
          45% {
            transform: translate3d(-42px, -2px, 0) rotate(-5deg);
          }
          68% {
            transform: translate3d(-16px, -20px, 0) rotate(5deg);
          }
        }
        @keyframes bot-shadow {
          0%, 100% {
            transform: scaleX(1);
            opacity: 0.7;
          }
          22%, 68% {
            transform: scaleX(0.72);
            opacity: 0.34;
          }
        }
        @keyframes bot-blink {
          0%, 92%, 100% {
            transform: scaleY(1);
          }
          95% {
            transform: scaleY(0.18);
          }
        }
        @keyframes bot-say-one {
          0%, 24% {
            opacity: 1;
          }
          28%, 100% {
            opacity: 0;
          }
        }
        @keyframes bot-say-two {
          0%, 28%, 64%, 100% {
            opacity: 0;
          }
          32%, 60% {
            opacity: 1;
          }
        }
        @keyframes bot-say-three {
          0%, 64% {
            opacity: 0;
          }
          68%, 96% {
            opacity: 1;
          }
          100% {
            opacity: 0;
          }
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
          border: none !important;
          border-radius: 0 !important;
          background: transparent !important;
          flex: 0 0 auto !important;
          box-shadow: none !important;
          padding: 0 4px !important;
          margin-top: -2px !important;
        }
        #admin-panel {
          border: 1px solid var(--line) !important;
          border-radius: 15px !important;
          background: white !important;
          flex: 0 0 auto !important;
          margin-top: 0 !important;
          overflow: hidden !important;
          box-shadow: 0 8px 22px rgba(88, 28, 135, 0.08) !important;
          position: relative !important;
          z-index: 20 !important;
          pointer-events: auto !important;
        }
        #admin-controls {
          gap: 8px;
          align-items: stretch;
          padding: 10px 12px 8px !important;
          position: relative !important;
          z-index: 22 !important;
          pointer-events: auto !important;
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
          min-height: 44px !important;
          width: 100% !important;
          cursor: pointer !important;
          pointer-events: auto !important;
          position: relative !important;
          z-index: 24 !important;
        }
        #admin-bookings {
          min-height: 92px !important;
          max-height: min(42dvh, 360px) !important;
          overflow-y: auto !important;
          padding: 0 12px 12px !important;
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
        .booking-card-list {
          display: grid;
          gap: 10px;
        }
        .booking-card {
          background: white;
          border: 1px solid rgba(168, 85, 247, 0.24);
          border-radius: 12px;
          padding: 12px;
          box-shadow: 0 8px 18px rgba(88, 28, 135, 0.06);
        }
        .booking-card-top,
        .booking-card-actions {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          flex-wrap: wrap;
        }
        .booking-card-top strong {
          color: #581c87;
          font-size: 0.9rem;
        }
        .booking-card-top span,
        .mail-status {
          border: 1px solid rgba(168, 85, 247, 0.26);
          border-radius: 999px;
          padding: 3px 8px;
          color: #581c87;
          font-size: 0.72rem;
          font-weight: 800;
          background: #fbf8ff;
        }
        .booking-card p {
          margin: 8px 0 0;
          display: grid;
          grid-template-columns: 64px minmax(0, 1fr);
          gap: 8px;
          color: var(--text);
          overflow-wrap: anywhere;
        }
        .booking-card p b {
          color: var(--muted);
        }
        .booking-card-actions {
          margin-top: 10px;
        }
        .booking-card-actions a {
          color: var(--accent-strong);
          font-weight: 850;
          text-decoration: none;
        }
        .booking-card small {
          display: block;
          margin-top: 8px;
          color: #b91c1c;
          overflow-wrap: anywhere;
        }
        #admin-panel summary,
        #admin-panel .label-wrap {
          color: var(--muted) !important;
          font-weight: 500 !important;
        }
        #admin-panel summary {
          min-height: 44px !important;
          padding: 0 14px !important;
          background: white !important;
          border-radius: 15px !important;
        }
        #admin-panel summary svg {
          color: var(--muted) !important;
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
          gap: 8px;
          flex-wrap: wrap;
          overflow-x: hidden !important;
          overflow-y: hidden !important;
          padding: 0 2px 0;
        }
        .suggestion-chip {
          border-radius: 15px !important;
          background: rgba(255, 255, 255, 0.42) !important;
          color: var(--text) !important;
          border: 1px solid rgba(168, 85, 247, 0.32) !important;
          min-height: 44px !important;
          min-width: 152px !important;
          max-width: none !important;
          flex: 1 1 152px !important;
          font-size: 0.82rem !important;
          line-height: 1.22 !important;
          font-weight: 750 !important;
          padding: 8px 12px !important;
          box-shadow: 0 8px 22px rgba(88, 28, 135, 0.08) !important;
          white-space: normal !important;
          backdrop-filter: blur(10px);
        }
        .suggestion-chip:hover {
          background: rgba(255, 255, 255, 0.78) !important;
          border-color: rgba(168, 85, 247, 0.65) !important;
        }
        @media (max-width: 520px) {
          .gradio-container {
            padding: 0 6px 8px !important;
          }
          .hero {
            margin: 0 -6px 0;
            padding: 10px 12px 9px;
          }
          .hero h1 {
            font-size: 1.14rem;
          }
          .hero p {
            font-size: 0.74rem;
          }
          #conversation-window {
            height: clamp(190px, calc(100dvh - 420px), 430px) !important;
            max-height: clamp(190px, calc(100dvh - 420px), 430px) !important;
            min-height: 170px !important;
            padding: 16px 12px 12px;
          }
          .mini-bot-row {
            min-height: 58px;
            justify-content: flex-end;
            margin-top: -10px;
            padding-right: 16px;
          }
          #mini-bot {
            width: 58px;
            height: 54px;
          }
          .bot-emoji {
            width: 38px;
            height: 38px;
            margin-top: 12px;
            border-radius: 14px;
            font-size: 1.25rem;
            box-shadow: 0 8px 18px rgba(126, 34, 206, 0.18);
          }
          .bot-speech {
            right: 28px;
            top: 1px;
            min-width: 44px;
            height: 22px;
            padding: 3px 6px;
            font-size: 0.62rem;
            border-radius: 10px 10px 4px 10px;
          }
          .bot-speech span {
            left: 6px;
            right: 6px;
          }
          .bot-shadow {
            width: 24px;
            height: 6px;
            margin-top: 2px;
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
          #suggestions-panel {
            padding: 0 2px !important;
          }
          .suggestion-chip {
            min-width: 132px !important;
            max-width: none !important;
            flex-basis: 132px !important;
            min-height: 42px !important;
            font-size: 0.8rem !important;
          }
        }
        .block-label {
          display: none !important;
        }
        footer { display: none !important; }
        """,
    )

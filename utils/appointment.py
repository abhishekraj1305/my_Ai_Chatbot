"""Free appointment-booking MVP helpers.

Google Calendar integration can be added later by setting up OAuth/service
account credentials outside source control and wiring them into the placeholder
functions below.
"""

from __future__ import annotations

import re
from typing import Dict, Tuple

from utils.booking_backend import available_slots, create_booking


APPOINTMENT_KEYWORDS = (
    "book call",
    "book a call",
    "appointment",
    "schedule",
    "meeting",
    "call with abhishek",
    "available slot",
    "availability",
)


def is_appointment_intent(message: str) -> bool:
    message = (message or "").lower()
    if "linkedin" in message or "github" in message:
        return False
    return any(keyword in message for keyword in APPOINTMENT_KEYWORDS)


def generate_jitsi_link() -> str:
    return "https://meet.jit.si/abhishek-portfolio-preview"


def extract_booking_details(message: str) -> dict:
    """Best-effort extraction for future form-based booking upgrades."""
    message = message or ""
    email_match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", message)
    date_match = re.search(
        r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}(?:\s+\d{4})?|today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        message,
        re.I,
    )
    time_match = re.search(
        r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)(?:\s*[A-Z]{2,5})?)\b",
        message,
    )
    return {
        "email": email_match.group(0) if email_match else None,
        "date": date_match.group(0) if date_match else None,
        "time": time_match.group(0) if time_match else None,
    }


def build_appointment_response(message: str) -> str:
    details = extract_booking_details(message)
    jitsi_link = generate_jitsi_link()
    email_hint = f"\nDetected email: {details['email']}" if details["email"] else ""

    return (
        "I can help with that. Please share these details so Abhishek can "
        "confirm the appointment:\n\n"
        "1. Name\n"
        "2. Email\n"
        "3. Preferred date\n"
        "4. Preferred time and timezone\n"
        "5. Purpose of the call\n\n"
        f"Free Jitsi meeting link draft: {jitsi_link}"
        f"{email_hint}\n\n"
        "Google Calendar is not connected yet, so this is a request flow for now."
    )


BOOKING_FIELDS = [
    ("name", "your name"),
    ("email", "your email address"),
    ("date", "your preferred date"),
    ("time", "your preferred time and timezone"),
    ("purpose", "the purpose of the call"),
]


def start_booking_state() -> Dict:
    return {"active": True, "step": "name", "details": {}}


def _next_missing_field(details: Dict) -> str | None:
    for field, _ in BOOKING_FIELDS:
        if not details.get(field):
            return field
    return None


def _field_prompt(field: str) -> str:
    labels = dict(BOOKING_FIELDS)
    return f"Sure. Please share {labels[field]}."


def _looks_like_name(message: str) -> bool:
    return bool(re.match(r"^[A-Za-z][A-Za-z .'-]{1,80}$", message.strip()))


def _is_confirmation(message: str) -> bool:
    lowered = message.lower().strip()
    return any(
        phrase in lowered
        for phrase in [
            "ok",
            "okay",
            "book it",
            "yes",
            "confirm",
            "go ahead",
            "that works",
            "sounds good",
        ]
    )


def _apply_slot_label(details: Dict, slot_label: str) -> None:
    match = re.search(
        r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}),\s*(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)(?:\s*IST)?)",
        slot_label,
    )
    if match:
        details["date"] = match.group(1)
        details["time"] = match.group(2)


def _apply_extracted_details(details: Dict, extracted: Dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if extracted.get(field):
            details[field] = extracted[field]


def _reset_invalid_slot_details(state: Dict, message: str) -> None:
    details = state.setdefault("details", {})
    lowered = message.lower()
    if "date/time" in lowered or "date" in lowered:
        details.pop("date", None)
        details.pop("time", None)
        state["step"] = "date"
    elif "time" in lowered or "past" in lowered:
        details.pop("time", None)
        state["step"] = "time"
    else:
        details.pop("date", None)
        details.pop("time", None)
        state["step"] = "date"


def _remaining_booking_text(message: str, extracted: Dict) -> str:
    remaining = message or ""
    for value in extracted.values():
        if value:
            remaining = re.sub(re.escape(value), " ", remaining, flags=re.I)
    remaining = re.sub(r"\b(ist|india|on|at|for|call|meeting|appointment)\b", " ", remaining, flags=re.I)
    remaining = re.sub(r"\s+", " ", remaining).strip(" .,-:")
    return remaining


def update_booking_state(message: str, state: Dict | None) -> Tuple[str, Dict]:
    """Collect booking details across turns without external calendar writes."""
    state = state or start_booking_state()
    details = state.setdefault("details", {})
    message = (message or "").strip()

    extracted = extract_booking_details(message)
    used_pending_slot = False
    if (
        state.get("step") == "time"
        and state.get("pending_slots")
        and _is_confirmation(message)
        and not extracted.get("date")
        and not extracted.get("time")
    ):
        _apply_slot_label(details, state["pending_slots"][0])
        state.pop("pending_slots", None)
        used_pending_slot = True

    current_field = state.get("step") if state.get("active") else _next_missing_field(details)
    if current_field not in {field for field, _ in BOOKING_FIELDS}:
        current_field = _next_missing_field(details)
    if used_pending_slot:
        current_field = _next_missing_field(details)
    if current_field == "name":
        _apply_extracted_details(details, extracted, ("email", "date", "time"))
        if _looks_like_name(message):
            details["name"] = message
        else:
            return "Please share your name so I can continue the booking request.", state
    elif current_field == "email":
        _apply_extracted_details(details, extracted, ("date", "time"))
        if extracted.get("email"):
            details["email"] = extracted["email"]
        else:
            return "Please share a valid email address.", state
    elif current_field == "date":
        if extracted.get("date"):
            details["date"] = extracted["date"]
            if extracted.get("time"):
                details["time"] = extracted["time"]
                state.pop("pending_slots", None)
                remaining = _remaining_booking_text(message, extracted)
                if remaining and not details.get("purpose") and len(remaining) >= 4:
                    details["purpose"] = remaining
        else:
            details["date"] = message
    elif current_field == "time":
        if extracted.get("date"):
            details["date"] = extracted["date"]
        if extracted.get("time"):
            details["time"] = extracted["time"]
            state.pop("pending_slots", None)
            remaining = _remaining_booking_text(message, extracted)
            if remaining and not details.get("purpose") and len(remaining) >= 4:
                details["purpose"] = remaining
        else:
            return "Please share your preferred time and timezone, for example: 4 PM IST.", state
    elif current_field == "purpose":
        if len(message) >= 4:
            details["purpose"] = message
        else:
            return "Please share the purpose of the call.", state

    next_field = _next_missing_field(details)
    if next_field:
        state["active"] = True
        state["step"] = next_field
        if next_field == "time" and details.get("date"):
            try:
                slots = available_slots(details["date"])
                if slots:
                    state["pending_slots"] = slots
                    return (
                        "These slots look available for that date:\n\n"
                        + "\n".join(f"- {slot}" for slot in slots)
                        + "\n\nPlease choose one, or type another time.",
                        state,
                    )
            except Exception:
                pass
        return _field_prompt(next_field), state

    booking = create_booking(details)
    if not booking.get("created"):
        if booking.get("reason") == "storage_error":
            state["active"] = True
            state["step"] = "purpose"
            return (
                "I collected the booking details, but could not save the request right now. "
                "Please try again in a moment, or contact Abhishek directly from the contact section.",
                state,
            )
        if booking.get("reason") == "parse_error":
            state["active"] = True
            _reset_invalid_slot_details(state, booking.get("message", ""))
            return (
                "I could not understand that date/time clearly. Please share it like: today 7 PM IST, 7 May 8 PM IST, or 15/05/2026 4 PM IST.",
                state,
            )
        state["active"] = True
        state["step"] = "time"
        alternatives = booking.get("available_slots") or []
        state["pending_slots"] = alternatives
        details.pop("time", None)
        if alternatives:
            response = (
                "That slot is already booked or unavailable. Please choose one of these available slots:\n\n"
                + "\n".join(f"- {slot}" for slot in alternatives)
                + "\n\nYou can reply with a listed time, or simply say 'okay book it' to choose the first slot."
            )
        else:
            response = "That slot is unavailable, and I cannot find another open slot for that date. Please try another date."
        return response, state

    state["active"] = False
    notification_note = (
        "Admin alert saved locally. Email alert will be sent when SMTP is configured."
        if not booking["notifications"]["owner_email_sent"]
        else "Abhishek has been notified by email."
    )
    response = (
        "Booked request received.\n\n"
        f"- Name: {booking['name']}\n"
        f"- Email: {booking['email']}\n"
        f"- Slot: {booking['slot_label']}\n"
        f"- Purpose: {booking['purpose']}\n\n"
        f"Meeting link: {booking['meeting_link']}\n\n"
        f"{notification_note}"
    )
    if booking.get("calendar_event_link"):
        response += f"\nCalendar event: {booking['calendar_event_link']}"
    response += "\nPlease keep this link safe until Abhishek confirms."
    return response, state


def check_availability(*args, **kwargs) -> dict:
    """Placeholder for Google Calendar availability checks.

    Later, load credentials from environment variables or a private credentials
    file ignored by git, then query the Calendar API here.
    """
    return {"available": None, "message": "Google Calendar is not configured yet."}


def create_google_calendar_event(*args, **kwargs) -> dict:
    """Placeholder for creating Google Calendar events.

    Do not hardcode credentials. Add OAuth/service account credentials through
    environment variables or Hugging Face Space secrets when upgrading.
    """
    return {"created": False, "message": "Google Calendar is not configured yet."}

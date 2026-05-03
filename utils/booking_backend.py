"""Booking availability, local reservations, and optional notifications.

This module works without paid services. It prevents double-booking locally via
`data/bookings.json`. If Google Calendar and SMTP credentials are added later,
the same flow can also check calendar busy times and send email notifications.
"""

from __future__ import annotations

import json
import os
import re
import smtplib
import uuid
from datetime import date, datetime, time, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except ImportError:  # Optional dependency for deployed calendar sync.
    service_account = None
    build = None


if load_dotenv:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

TIMEZONE = ZoneInfo(os.getenv("BOOKING_TIMEZONE", "Asia/Kolkata"))
BOOKINGS_PATH = Path(
    os.getenv(
        "BOOKINGS_PATH",
        str(Path(__file__).resolve().parents[1] / "data" / "bookings.json"),
    )
)
DEFAULT_OWNER_EMAIL = "r.abhishek1305@gmail.com"


def _env_value(name: str) -> str:
    return (os.getenv(name) or "").strip()


def smtp_is_configured() -> bool:
    return all(_env_value(name) for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))


def owner_email() -> str:
    return _env_value("OWNER_EMAIL") or DEFAULT_OWNER_EMAIL


def _load_bookings() -> List[Dict]:
    if not BOOKINGS_PATH.exists():
        return []
    try:
        return json.loads(BOOKINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_bookings(bookings: List[Dict]) -> None:
    BOOKINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOOKINGS_PATH.write_text(json.dumps(bookings, indent=2), encoding="utf-8")


def list_bookings(limit: int = 50) -> List[Dict]:
    """Return bookings sorted by meeting slot for the admin dashboard."""
    bookings = _load_bookings()
    bookings.sort(key=lambda item: item.get("slot_key", ""))
    return bookings[:limit]


def _parse_date(date_text: str) -> date:
    text = (date_text or "").strip().lower()
    text = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", text)
    today = datetime.now(TIMEZONE).date()
    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)

    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    if text in weekdays:
        days_ahead = (weekdays[text] - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return today + timedelta(days=days_ahead)

    for fmt in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%Y-%m-%d",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    for fmt in ("%d %b", "%d %B"):
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue

        candidate = date(today.year, parsed.month, parsed.day)
        if candidate < today:
            candidate = date(today.year + 1, parsed.month, parsed.day)
        return candidate

    raise ValueError("Could not understand the date.")


def _parse_time(time_text: str) -> time:
    text = (time_text or "").strip().lower()
    text = (
        text.replace("ist", "")
        .replace("india", "")
        .replace("today", "")
        .replace("tomorrow", "")
        .strip()
    )
    text = text.replace(".", "")
    text = re.sub(r"^(\d{1,2})(am|pm)$", r"\1 \2", text)
    text = re.sub(r"^(\d{1,2}:\d{2})(am|pm)$", r"\1 \2", text)
    for fmt in ("%I:%M %p", "%I %p", "%H:%M", "%H"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            pass

    raise ValueError("Could not understand the time.")


def parse_slot(date_text: str, time_text: str) -> datetime:
    slot_date = _parse_date(date_text)
    slot_time = _parse_time(time_text)
    slot_start = datetime.combine(slot_date, slot_time, tzinfo=TIMEZONE)
    if slot_start <= datetime.now(TIMEZONE):
        raise ValueError("That date/time is already in the past.")
    return slot_start


def _slot_key(slot_start: datetime) -> str:
    return slot_start.astimezone(TIMEZONE).strftime("%Y-%m-%dT%H:%M")


def is_slot_available(slot_start: datetime) -> bool:
    slot_key = _slot_key(slot_start)
    for booking in _load_bookings():
        if booking.get("slot_key") == slot_key and booking.get("status") != "cancelled":
            return False
    if _is_busy_on_google_calendar(slot_start):
        return False
    return True


def _google_calendar_service():
    if service_account is None or build is None:
        return None

    credentials_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
    if not credentials_file or not calendar_id or not Path(credentials_file).exists():
        return None

    scopes = ["https://www.googleapis.com/auth/calendar"]
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file, scopes=scopes
    )
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _is_busy_on_google_calendar(slot_start: datetime) -> bool:
    service = _google_calendar_service()
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
    if not service or not calendar_id:
        return False

    slot_end = slot_start + timedelta(minutes=int(os.getenv("BOOKING_DURATION_MINUTES", "30")))
    body = {
        "timeMin": slot_start.astimezone(timezone.utc).isoformat(),
        "timeMax": slot_end.astimezone(timezone.utc).isoformat(),
        "items": [{"id": calendar_id}],
    }
    try:
        result = service.freebusy().query(body=body).execute()
        busy = result.get("calendars", {}).get(calendar_id, {}).get("busy", [])
        return bool(busy)
    except Exception:
        return False


def _create_google_calendar_event(booking: Dict) -> str | None:
    service = _google_calendar_service()
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
    if not service or not calendar_id:
        return None

    slot_start = datetime.strptime(booking["slot_key"], "%Y-%m-%dT%H:%M").replace(tzinfo=TIMEZONE)
    slot_end = slot_start + timedelta(minutes=int(os.getenv("BOOKING_DURATION_MINUTES", "30")))
    event = {
        "summary": f"Call with {booking['name']} - Portfolio chatbot",
        "description": (
            f"Purpose: {booking['purpose']}\n"
            f"Visitor email: {booking['email']}\n"
            f"Meeting link: {booking['meeting_link']}"
        ),
        "start": {"dateTime": slot_start.isoformat(), "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": slot_end.isoformat(), "timeZone": "Asia/Kolkata"},
        "attendees": [{"email": booking["email"]}],
        "location": booking["meeting_link"],
    }
    try:
        created = service.events().insert(calendarId=calendar_id, body=event).execute()
        return created.get("htmlLink")
    except Exception:
        return None


def available_slots(date_text: str, limit: int = 12) -> List[str]:
    slot_date = _parse_date(date_text)
    now = datetime.now(TIMEZONE)
    candidates = []
    for hour in (10, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22):
        slot = datetime.combine(slot_date, time(hour=hour), tzinfo=TIMEZONE)
        if slot <= now:
            continue
        if is_slot_available(slot):
            candidates.append(slot.strftime("%d %b %Y, %I:%M %p IST"))
        if len(candidates) >= limit:
            break
    return candidates


def _send_email(subject: str, body: str, to_email: str) -> bool:
    host = _env_value("SMTP_HOST")
    user = _env_value("SMTP_USER")
    password = _env_value("SMTP_PASSWORD").replace(" ", "")
    if not host or not user or not password:
        return False

    port = int(_env_value("SMTP_PORT") or "587")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = user
    message["To"] = to_email
    message.set_content(body)

    with smtplib.SMTP(host, port, timeout=25) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(message)
    return True


def notify_booking(booking: Dict) -> Dict:
    body = (
        "New portfolio chatbot booking request\n\n"
        f"Name: {booking['name']}\n"
        f"Email: {booking['email']}\n"
        f"Slot: {booking['slot_label']}\n"
        f"Purpose: {booking['purpose']}\n"
        f"Meeting: {booking['meeting_link']}\n"
    )
    notification_errors = []
    configured = smtp_is_configured()
    if not configured:
        notification_errors.append("SMTP credentials are not configured in the runtime environment.")

    try:
        owner_sent = _send_email("New chatbot booking request", body, owner_email())
    except Exception as exc:
        owner_sent = False
        notification_errors.append(f"owner email failed: {exc}")
        print(f"[booking] owner email failed: {type(exc).__name__}: {exc}")

    try:
        visitor_sent = _send_email(
            "Your call request with Abhishek",
            "Thanks for requesting a call with Abhishek.\n\n" + body,
            booking["email"],
        )
    except Exception as exc:
        visitor_sent = False
        notification_errors.append(f"visitor email failed: {exc}")
        print(f"[booking] visitor email failed: {type(exc).__name__}: {exc}")

    if not owner_sent:
        try:
            log_path = BOOKINGS_PATH.parent / "booking_notifications.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n--- {datetime.now(TIMEZONE).isoformat()} ---\n{body}\n")
                if notification_errors:
                    handle.write("Notification errors:\n")
                    for error in notification_errors:
                        handle.write(f"- {error}\n")
        except Exception as exc:
            notification_errors.append(f"local notification log failed: {exc}")

    return {
        "smtp_configured": configured,
        "owner_email_sent": owner_sent,
        "visitor_email_sent": visitor_sent,
        "errors": notification_errors,
    }


def create_booking(details: Dict) -> Dict:
    try:
        slot_start = parse_slot(details["date"], details["time"])
    except ValueError as exc:
        return {"created": False, "reason": "parse_error", "message": str(exc)}
    if not is_slot_available(slot_start):
        return {
            "created": False,
            "reason": "slot_unavailable",
            "available_slots": available_slots(details["date"]),
        }

    meeting_link = f"https://meet.jit.si/abhishek-portfolio-{uuid.uuid4().hex[:10]}"
    booking = {
        "id": uuid.uuid4().hex[:12],
        "name": details["name"],
        "email": details["email"],
        "purpose": details["purpose"],
        "slot_key": _slot_key(slot_start),
        "slot_label": slot_start.strftime("%d %b %Y, %I:%M %p IST"),
        "meeting_link": meeting_link,
        "status": "requested",
        "created_at": datetime.now(TIMEZONE).isoformat(),
    }
    try:
        bookings = _load_bookings()
        bookings.append(booking)
        _save_bookings(bookings)
    except Exception as exc:
        return {
            "created": False,
            "reason": "storage_error",
            "message": f"Could not save the booking request: {exc}",
        }
    booking["calendar_event_link"] = _create_google_calendar_event(booking)
    booking["notifications"] = notify_booking(booking)
    booking["notification_errors"] = booking["notifications"].get("errors", [])
    booking["created"] = True
    try:
        bookings = _load_bookings()
        for index, item in enumerate(bookings):
            if item.get("id") == booking["id"]:
                bookings[index] = booking
                break
        _save_bookings(bookings)
    except Exception as exc:
        booking.setdefault("notification_errors", []).append(
            f"booking notification status update failed: {exc}"
        )
    return booking

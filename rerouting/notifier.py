"""
Departure-aware email alerts ("2 hours before the flight").

Every NOTIFY_POLL_S seconds (default 300) the rerouting API checks all
un-notified subscriptions. When a subscriber's flight departs within
ALERT_LEAD_H hours (default 2) AND is disrupted — CANCELLED/DELAYED on the
airport board, or the fog model fires — they receive ONE email and the
subscription is marked notified.

Required env (on the rerouting API):
    SUPABASE_CONN_STRING  - where subscriptions live
    RESEND_API_KEY        - to actually send (free key: https://resend.com)
Optional:
    EMAIL_FROM     (default onboarding@resend.dev)
    ALERT_LEAD_H   (default 2 — "email N hours before departure")
    NOTIFY_POLL_S  (default 300)

Tip: configure RESEND_API_KEY here and NOT on the ML service — the ML
service's own email path blasts every subscriber as soon as fog is detected,
without per-flight timing. This notifier replaces that behaviour.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta

import requests

try:
    import psycopg2
    _HAS_PSYCOPG2 = True
except ImportError:
    _HAS_PSYCOPG2 = False

logger = logging.getLogger(__name__)

ALERT_LEAD_H  = float(os.environ.get("ALERT_LEAD_H", "2"))
NOTIFY_POLL_S = int(os.environ.get("NOTIFY_POLL_S", "300"))

_RESEND_KEY = os.environ.get("RESEND_API_KEY", "")
_EMAIL_FROM = os.environ.get("EMAIL_FROM", "onboarding@resend.dev")


def enabled(conn_string: str | None) -> bool:
    return bool(conn_string and _RESEND_KEY and _HAS_PSYCOPG2)


def decide(status: str, fog_alert: str | None) -> str | None:
    """Disruption kind for a flight inside the alert window, or None."""
    if status == "CANCELLED" or fog_alert == "full_risk":
        return "canceled"
    if status in ("DELAYED", "FOG_RISK") or fog_alert == "early_warning":
        return "warning"
    return None


def _departure(route: dict) -> datetime | None:
    """Scheduled departure as naive local datetime.

    Falls back to the same placeholder /flight shows for demo-DB flights
    (tomorrow 08:00), so demo subscriptions are notifiable too.
    """
    s = route.get("scheduled_departure")
    if s:
        try:
            return datetime.fromisoformat(s).replace(tzinfo=None)
        except ValueError:
            return None
    return (datetime.now() + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )


def send_email(to: str, flight_code: str, kind: str, departs: datetime) -> bool:
    dep_str = departs.strftime("%H:%M on %d %b")

    if kind == "canceled":
        subject = f"✈️ FLIGHT CANCELED — {flight_code} (fog at Iași)"
        color, heading = "#D62828", f"Flight {flight_code} has been CANCELED"
        body = (
            f"Due to dense fog at Iași Airport (LRIA), your flight <b>{flight_code}</b> "
            f"(scheduled {dep_str}) has been canceled."
        )
        cta = "Open the app to claim a refund or find alternative routes."
    else:
        subject = f"⚠️ FOG WARNING — {flight_code} departs at {departs:%H:%M}"
        color, heading = "#F5A623", f"Fog risk for flight {flight_code}"
        body = (
            f"Your flight <b>{flight_code}</b>, scheduled at <b>{dep_str}</b>, "
            f"may be affected by fog at Iași Airport (LRIA)."
        )
        cta = "Open the app to monitor your flight and check alternatives."

    html = f"""
    <div style="font-family:system-ui,sans-serif;max-width:540px;margin:auto;background:#f5f7fa;border-radius:12px;overflow:hidden">
      <div style="background:{color};padding:28px 32px">
        <h1 style="margin:0;color:#fff;font-size:22px">{heading}</h1>
      </div>
      <div style="padding:28px 32px;background:#fff">
        <p style="margin:0 0 16px;font-size:16px;color:#0A0F1E;line-height:1.6">{body}</p>
        <p style="margin:0 0 24px;font-size:15px;color:#4A5568">{cta}</p>
        <p style="margin:0;font-size:12px;color:#999">
          You are receiving this because you subscribed to alerts for flight {flight_code}.
        </p>
      </div>
    </div>"""

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {_RESEND_KEY}", "Content-Type": "application/json"},
        json={"from": _EMAIL_FROM, "to": [to], "subject": subject, "html": html},
        timeout=15,
    )
    return resp.ok


def check_once(conn_string: str, resolve_fn, fog_fn, send_fn=send_email) -> dict:
    """One notification pass. Returns {'checked': n, 'sent': n}."""
    conn = psycopg2.connect(conn_string)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT email, flight_number FROM passenger_notifications WHERE notified = false"
            )
            subs = cur.fetchall()
    finally:
        conn.close()

    now = datetime.now()
    sent = 0
    fog_cache: dict[str, str | None] = {}

    for email, flight_number in subs:
        key, route = resolve_fn(flight_number)
        if not route:
            continue
        departs = _departure(route)
        if departs is None or not (now <= departs <= now + timedelta(hours=ALERT_LEAD_H)):
            continue  # outside the "ALERT_LEAD_H hours before departure" window

        if key not in fog_cache:
            fog_cache[key] = fog_fn(key)
        kind = decide(route.get("status", "ON_TIME"), fog_cache[key])
        if not kind:
            continue  # flight departs soon but is fine — stay silent

        if send_fn(email, key, kind, departs):
            sent += 1
            conn = psycopg2.connect(conn_string)
            try:
                with conn, conn.cursor() as cur:
                    cur.execute(
                        "UPDATE passenger_notifications "
                        "SET notified = true, notified_at = NOW() "
                        "WHERE email = %s AND flight_number = %s",
                        (email, flight_number),
                    )
            finally:
                conn.close()
            logger.info("Notified %s about %s (%s)", email, key, kind)

    return {"checked": len(subs), "sent": sent}


async def loop(conn_string: str, resolve_fn, fog_fn) -> None:
    """Background poller — started from the API's lifespan when enabled()."""
    logger.info(
        "Departure-aware notifier started (lead=%.1fh, poll=%ds)", ALERT_LEAD_H, NOTIFY_POLL_S
    )
    while True:
        try:
            result = await asyncio.to_thread(check_once, conn_string, resolve_fn, fog_fn)
            if result["sent"]:
                logger.info("Notifier pass: %s", result)
        except Exception as exc:
            logger.warning("Notifier pass failed: %s", exc)
        await asyncio.sleep(NOTIFY_POLL_S)

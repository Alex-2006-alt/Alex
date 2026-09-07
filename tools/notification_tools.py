"""
ALEX — Notification & Reminder Tools
Desktop notifications, Windows toast alerts, and reminders.
"""

import threading
from datetime import datetime, timedelta

from core.tool_registry import tool, ToolResult
from utils.logger import log


@tool(
    name="notify",
    description="Show a Windows desktop notification/toast message to the user",
    parameters={
        "title": {"type": "string", "description": "Notification title", "required": True},
        "message": {"type": "string", "description": "Notification body text", "required": True},
        "duration": {"type": "integer", "description": "How long to show (seconds, default: 5)", "required": False},
    },
    category="notifications",
)
def notify(params: dict) -> ToolResult:
    title = params.get("title", "Alex")
    message = params.get("message", "")
    duration = int(params.get("duration", 5))

    log.info(f"🔔 Desktop notification: {title} — {message}")

    # Print to console always
    print(f"\n{'='*50}\n  🔔 {title}\n  {message}\n{'='*50}\n")

    # Try Windows toast notification
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=duration, threaded=True)
        return ToolResult(success=True, message=f"Notification sent: {title}")
    except ImportError:
        pass

    # Fallback: try plyer
    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=duration)
        return ToolResult(success=True, message=f"Notification sent: {title}")
    except ImportError:
        pass

    # Fallback: just printed to console
    return ToolResult(success=True, message=f"Notification (console): {title} — {message}")


@tool(
    name="reminder_set",
    description="Set a timed reminder that will alert you after a specified time",
    parameters={
        "message": {"type": "string", "description": "Reminder message to display", "required": True},
        "minutes": {"type": "integer", "description": "Minutes from now (default: 5)", "required": False},
        "hours": {"type": "integer", "description": "Hours from now (default: 0)", "required": False},
    },
    category="notifications",
)
def reminder_set(params: dict) -> ToolResult:
    message = params.get("message", "Time's up!")
    minutes = int(params.get("minutes", 5))
    hours = int(params.get("hours", 0))

    total_minutes = minutes + (hours * 60)
    trigger_time = datetime.now() + timedelta(minutes=total_minutes)

    def _trigger():
        log.info(f"⏰ REMINDER triggered: {message}")
        # Speak it
        try:
            from core.speaker import Speaker
            Speaker().say(f"Reminder: {message}")
        except Exception:
            pass
        # Show notification
        notify({"title": "⏰ Reminder", "message": message, "duration": 10})

    timer = threading.Timer(total_minutes * 60, _trigger)
    timer.daemon = True
    timer.start()

    time_desc = f"{total_minutes} minute{'s' if total_minutes != 1 else ''}"
    if hours:
        time_desc = f"{hours}h {minutes}m"

    log.info(f"⏰ Reminder set for {total_minutes} minutes: {message}")
    return ToolResult(
        success=True,
        message=f"Reminder set! I'll alert you in {time_desc}: \"{message}\"",
        data={"message": message, "trigger_time": trigger_time.isoformat(), "minutes": total_minutes},
    )


@tool(
    name="weather_get",
    description="Get current weather information for a city",
    parameters={
        "city": {"type": "string", "description": "City name (or 'auto' to detect location)", "required": True},
    },
    category="notifications",
)
def weather_get(params: dict) -> ToolResult:
    import requests
    import config

    city = params.get("city", "London")

    if city == "auto":
        # Try to get location from IP
        try:
            resp = requests.get("https://ipapi.co/json/", timeout=5)
            geo = resp.json()
            city = geo.get("city", "London")
        except Exception:
            city = "London"

    api_key = config.OPENWEATHER_API_KEY
    if not api_key:
        # Use wttr.in (no API key needed)
        try:
            resp = requests.get(f"https://wttr.in/{city}?format=j1", timeout=10)
            data = resp.json()
            current = data["current_condition"][0]
            temp_c = current["temp_C"]
            feels_like = current["FeelsLikeC"]
            desc = current["weatherDesc"][0]["value"]
            humidity = current["humidity"]
            wind = current["windspeedKmph"]
            return ToolResult(
                success=True,
                message=f"Weather in {city}: {desc}, {temp_c}°C (feels like {feels_like}°C), humidity {humidity}%, wind {wind} km/h",
                data={"city": city, "temp_c": temp_c, "description": desc, "humidity": humidity},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Could not get weather: {e}")

    # Use OpenWeatherMap
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
        resp = requests.get(url, timeout=10)
        data = resp.json()

        if resp.status_code != 200:
            return ToolResult(success=False, error=data.get("message", "Weather API error"))

        temp = data["main"]["temp"]
        feels = data["main"]["feels_like"]
        desc = data["weather"][0]["description"].capitalize()
        humidity = data["main"]["humidity"]
        wind = data["wind"]["speed"]
        city_name = data["name"]

        return ToolResult(
            success=True,
            message=f"Weather in {city_name}: {desc}, {temp:.1f}°C (feels like {feels:.1f}°C), humidity {humidity}%, wind {wind} m/s",
            data=data,
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Weather request failed: {e}")


@tool(
    name="email_send",
    description="Send an email via configured SMTP server",
    parameters={
        "to": {"type": "string", "description": "Recipient email address", "required": True},
        "subject": {"type": "string", "description": "Email subject line", "required": True},
        "body": {"type": "string", "description": "Email body text", "required": True},
        "cc": {"type": "string", "description": "CC email address (optional)", "required": False},
    },
    category="notifications",
)
def email_send(params: dict) -> ToolResult:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import config

    to = params.get("to", "")
    subject = params.get("subject", "")
    body = params.get("body", "")
    cc = params.get("cc", "")

    if not all([to, subject, body]):
        return ToolResult(success=False, error="Missing required fields: to, subject, body")

    if not config.EMAIL_ADDRESS or not config.EMAIL_PASSWORD:
        return ToolResult(success=False, error="Email credentials not configured. Set EMAIL_ADDRESS and EMAIL_PASSWORD in .env")

    try:
        msg = MIMEMultipart()
        msg["From"] = config.EMAIL_ADDRESS
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(config.EMAIL_SMTP_HOST, config.EMAIL_SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
            server.send_message(msg)

        log.info(f"📧 Email sent to {to}: {subject}")
        return ToolResult(success=True, message=f"Email sent to {to}: '{subject}'")
    except Exception as e:
        return ToolResult(success=False, error=f"Email failed: {e}")

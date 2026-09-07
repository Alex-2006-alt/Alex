"""
ALEX — Email Plugin
Send emails via SMTP (Gmail, Outlook, etc).
Requires EMAIL_ADDRESS, EMAIL_PASSWORD, and EMAIL_SMTP_HOST in .env
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from plugins.plugin_loader import PluginBase
from utils.logger import log
import config


class EmailPlugin(PluginBase):
    """Send emails via SMTP."""

    name = "email"
    description = "Send emails using your configured email account"
    actions = ["send_email"]

    def __init__(self):
        self.smtp_host = config.EMAIL_SMTP_HOST
        self.smtp_port = config.EMAIL_SMTP_PORT
        self.email_address = config.EMAIL_ADDRESS
        self.email_password = config.EMAIL_PASSWORD

    def execute(self, params: dict) -> str:
        """
        Send an email.

        Params:
            to: Recipient email address
            subject: Email subject line
            body: Email body text
            html: (optional) HTML body content
        """
        to = params.get("to", "")
        subject = params.get("subject", "Message from ALEX")
        body = params.get("body", "")
        html = params.get("html", "")

        # Validation
        if not self.email_address or not self.email_password:
            return (
                "Email plugin is not configured. "
                "Add EMAIL_ADDRESS and EMAIL_PASSWORD to your .env file. "
                "For Gmail, use an App Password: https://myaccount.google.com/apppasswords"
            )

        if not to:
            return "No recipient specified. Please provide a 'to' email address."

        if not body and not html:
            return "No email body provided. Please specify what you'd like to say."

        if "@" not in to:
            return f"'{to}' doesn't look like a valid email address."

        try:
            # Build the email
            msg = MIMEMultipart("alternative")
            msg["From"] = self.email_address
            msg["To"] = to
            msg["Subject"] = subject

            # Attach plain text body
            msg.attach(MIMEText(body, "plain"))

            # Attach HTML body if provided
            if html:
                msg.attach(MIMEText(html, "html"))

            # Connect and send
            context = ssl.create_default_context()

            if self.smtp_port == 465:
                # SSL connection
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context) as server:
                    server.login(self.email_address, self.email_password)
                    server.sendmail(self.email_address, to, msg.as_string())
            else:
                # STARTTLS connection (port 587)
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(self.email_address, self.email_password)
                    server.sendmail(self.email_address, to, msg.as_string())

            log.info(f"📧 Email sent to {to}: \"{subject}\"")
            return f"Email sent successfully to {to} with subject \"{subject}\"."

        except smtplib.SMTPAuthenticationError:
            return (
                "Email authentication failed. Check your EMAIL_ADDRESS and EMAIL_PASSWORD. "
                "If using Gmail, make sure you're using an App Password, not your regular password."
            )
        except smtplib.SMTPRecipientsRefused:
            return f"The recipient address '{to}' was rejected by the mail server."
        except smtplib.SMTPException as e:
            return f"SMTP error while sending email: {e}"
        except Exception as e:
            log.error(f"Email send error: {e}")
            return f"Error sending email: {e}"

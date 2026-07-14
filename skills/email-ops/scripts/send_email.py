#!/usr/bin/env python3
"""
send_email.py — Send a single plain-text email via SMTP.

Uses Python's built-in smtplib only — no third-party dependencies.

Environment Variables:
  SMTP_SERVER    SMTP hostname (e.g., smtp.gmail.com, smtp.qq.com)
  SMTP_PORT      Port — 587 for STARTTLS (default), 465 for SSL
  SMTP_USER      Login username (usually the sender email address)
  SMTP_PASSWORD  Password or app-specific password
  SMTP_FROM      Optional display name + address (e.g., "张三 <you@gmail.com>")
                 Defaults to SMTP_USER if not set.

Usage:
  python3 send_email.py --to recipient@example.com --subject "Hello" --body "Message"
  python3 send_email.py --to recipient@example.com --subject "Hello" --body-file ./template.txt

Output (JSON to stdout):
  {"ok": true,  "to": "recipient@example.com", "message": "sent"}
  {"ok": false, "to": "recipient@example.com", "error": "..."}
"""

import argparse
import json
import os
import smtplib
import ssl
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, parseaddr


def get_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def require_env(name: str) -> str:
    val = get_env(name)
    if not val:
        result = {"ok": False, "to": "", "error": f"Environment variable {name} is not set"}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)
    return val


def send(to: str, subject: str, body: str) -> dict:
    smtp_server = require_env("SMTP_SERVER")
    smtp_port = int(get_env("SMTP_PORT", "587"))
    smtp_user = require_env("SMTP_USER")
    smtp_password = require_env("SMTP_PASSWORD")
    smtp_from_raw = get_env("SMTP_FROM") or smtp_user

    # Build the From header
    display_name, from_addr = parseaddr(smtp_from_raw)
    if not from_addr:
        from_addr = smtp_from_raw
        display_name = ""
    from_header = formataddr((display_name, from_addr)) if display_name else from_addr

    # Build message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_header
    msg["To"] = to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        if smtp_port == 465:
            # SSL from the start
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, [to], msg.as_string())
        else:
            # STARTTLS (port 587 or 25)
            with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, [to], msg.as_string())

        return {"ok": True, "to": to, "message": "sent"}

    except smtplib.SMTPAuthenticationError as e:
        return {"ok": False, "to": to, "error": f"Authentication failed: {e.smtp_error.decode(errors='replace')}"}
    except smtplib.SMTPRecipientsRefused as e:
        return {"ok": False, "to": to, "error": f"Recipient refused: {e}"}
    except smtplib.SMTPDataError as e:
        return {"ok": False, "to": to, "error": f"Data error (possible spam rejection): {e.smtp_error.decode(errors='replace')}"}
    except smtplib.SMTPConnectError as e:
        return {"ok": False, "to": to, "error": f"Cannot connect to {smtp_server}:{smtp_port} — check SMTP_SERVER and SMTP_PORT"}
    except TimeoutError:
        return {"ok": False, "to": to, "error": f"Connection timed out to {smtp_server}:{smtp_port}"}
    except Exception as e:
        return {"ok": False, "to": to, "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a single email via SMTP")
    parser.add_argument("--to", required=True, help="Recipient email address")
    parser.add_argument("--subject", required=True, help="Email subject line")

    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="Email body text (plain text)")
    body_group.add_argument("--body-file", help="Path to a file containing the email body")

    args = parser.parse_args()

    if args.body_file:
        try:
            with open(args.body_file, "r", encoding="utf-8") as f:
                body = f.read()
        except FileNotFoundError:
            result = {"ok": False, "to": args.to, "error": f"Body file not found: {args.body_file}"}
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(1)
    else:
        body = args.body

    result = send(to=args.to, subject=args.subject, body=body)
    print(json.dumps(result, ensure_ascii=False))

    if not result["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

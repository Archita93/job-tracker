#!/usr/bin/env python3
"""
New Grad Job Tracker (Canada) - Data/ML focus
Source: Adzuna API (Canada) - legitimate aggregator, official API

Keeps a JSON file of previously-seen job IDs/links so only NEW postings are reported.
"""

import os
import sys
import json
import smtplib
import argparse
from email.mime.text import MIMEText
from datetime import datetime, timezone

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")

# Email delivery (Gmail SMTP with an App Password)
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")

# Keywords for "new grad" data/ML roles
KEYWORDS = [
    "new grad data",
    "new graduate data scientist",
    "new graduate data analyst",
    "entry level data scientist",
    "entry level machine learning",
    "graduate machine learning engineer",
    "junior data analyst",
    "junior data scientist",
]

ADZUNA_COUNTRY = "ca"
ADZUNA_RESULTS_PER_PAGE = 20
ADZUNA_MAX_DAYS_OLD = 3  # only recent postings

SEEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen_jobs.json")


# ---------------------------------------------------------------------------
# Seen-jobs store
# ---------------------------------------------------------------------------

def load_seen(path=SEEN_FILE):
    if os.path.exists(path):
        with open(path, "r") as f:
            try:
                return set(json.load(f))
            except json.JSONDecodeError:
                return set()
    return set()


def save_seen(seen, path=SEEN_FILE):
    with open(path, "w") as f:
        json.dump(sorted(seen), f, indent=2)


# ---------------------------------------------------------------------------
# Source: Adzuna API
# ---------------------------------------------------------------------------

def fetch_adzuna_jobs(app_id, app_key, keywords, seen):
    """Query Adzuna's Canada job search endpoint for each keyword; return new postings."""
    new_jobs = []

    if not app_id or not app_key:
        print("  [Adzuna] Skipped: no App ID / App Key configured.", file=sys.stderr)
        return new_jobs

    for kw in keywords:
        url = f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": ADZUNA_RESULTS_PER_PAGE,
            "what": kw,
            "max_days_old": ADZUNA_MAX_DAYS_OLD,
            "sort_by": "date",
            "content-type": "application/json",
        }
        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"  [Adzuna] Error fetching '{kw}': {e}", file=sys.stderr)
            continue

        for job in data.get("results", []):
            job_id = f"adzuna:{job.get('id')}"
            if job_id in seen:
                continue
            new_jobs.append({
                "id": job_id,
                "source": "Adzuna",
                "title": job.get("title", "").strip(),
                "company": (job.get("company") or {}).get("display_name", "Unknown"),
                "location": (job.get("location") or {}).get("display_name", "Canada"),
                "url": job.get("redirect_url", ""),
                "created": job.get("created", ""),
                "keyword": kw,
            })
            seen.add(job_id)

    return new_jobs


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_report(jobs):
    if not jobs:
        return "No new grad data/ML postings found since the last check."

    lines = [f"**{len(jobs)} new posting(s) found:**\n"]
    for j in jobs:
        lines.append(
            f"- **{j['title']}** — {j['company']} ({j['location']})\n"
            f"  Source: {j['source']} | {j['url']}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

def send_email(subject, body, gmail_address, app_password, to_addr):
    """Send a plain-text email via Gmail SMTP using an App Password."""
    if not (gmail_address and app_password and to_addr):
        print("  [Email] Skipped: missing GMAIL_ADDRESS / GMAIL_APP_PASSWORD / EMAIL_TO.", file=sys.stderr)
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = to_addr

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, [to_addr], msg.as_string())
        print(f"  [Email] Sent to {to_addr}.", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  [Email] Error sending: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="New grad job tracker (Canada)")
    parser.add_argument("--seen-file", default=SEEN_FILE, help="Path to seen-jobs JSON store")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist seen-jobs updates")
    parser.add_argument("--json-out", action="store_true", help="Print raw JSON instead of formatted text")
    parser.add_argument("--email", action="store_true", help="Email the report using GMAIL_ADDRESS/GMAIL_APP_PASSWORD/EMAIL_TO")
    parser.add_argument("--email-even-if-empty", action="store_true", help="Send an email even when there are no new postings")
    args = parser.parse_args()

    seen = load_seen(args.seen_file)
    starting_count = len(seen)

    print(f"[{datetime.now(timezone.utc).isoformat()}] Checking for new postings...", file=sys.stderr)

    all_new = []
    print("Querying Adzuna...", file=sys.stderr)
    all_new.extend(fetch_adzuna_jobs(ADZUNA_APP_ID, ADZUNA_APP_KEY, KEYWORDS, seen))

    if not args.dry_run:
        save_seen(seen, args.seen_file)

    print(f"Seen-store: {starting_count} -> {len(seen)} entries.", file=sys.stderr)

    report = format_report(all_new)

    if args.json_out:
        print(json.dumps(all_new, indent=2))
    else:
        print(report)

    if args.email and (all_new or args.email_even_if_empty):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        subject = f"New Grad Data/ML Jobs (Canada) - {today} - {len(all_new)} new"
        send_email(subject, report, GMAIL_ADDRESS, GMAIL_APP_PASSWORD, EMAIL_TO)


if __name__ == "__main__":
    main()
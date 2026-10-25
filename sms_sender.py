
#!/usr/bin/env python3
"""
Proof-of-concept email-to-SMS sender.
Reads numbers from a CSV, converts each to a carrier gateway email,
and sends through the configured SMTP server.
"""

import csv
import smtplib
import ssl
import time
from email.message import EmailMessage

# ---------------- CONFIG ----------------
SMTP_HOST = "mail.privateemail.com"
SMTP_PORT = 587 # 587 = STARTTLS
SMTP_USER = "newbox8902@maketheworldd.com"
SMTP_PASS = "Smtppassword3$"
FROM_ADDR = "newbox8902@maketheworldd.com"
FROM_NAME = "Test Sender"

# "manual"  -> use the 'carrier' column in the CSV
# "shotgun" -> send to ALL carriers (phone gets duplicates)
CARRIER_MODE = "manual"

# True = print only, don't send. Set False to actually send.
DRY_RUN = False

SEND_DELAY = 1.0                      # seconds between sends

# {name} is replaced per-row if a 'name' column exists
MESSAGE = "Hello {name}! This is a test message from our bulk SMS tool."

INPUT_CSV = "numbers.csv"
LOG_CSV = "results.csv"
# ----------------------------------------

GATEWAYS = {
    "att": "txt.att.net",
    "verizon": "vtext.com",
    "tmobile": "tmomail.net",
    "sprint": "messaging.sprintpcs.com",
    "uscellular": "email.uscc.net",
    "boost": "sms.myboostmobile.com",
    "cricket": "sms.cricketwireless.net",
    "metro": "mymetropcs.com",
    "googlefi": "msg.fi.google.com",
    "mint": "tmomail.net",
}


def normalize_phone(raw):
    """Strip everything but digits. Return 10-digit US number."""
    digits = "".join(c for c in str(raw) if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def gateway_addresses(phone, carrier):
    """Return the gateway email address(es) to send to."""
    if CARRIER_MODE == "shotgun":
        return [f"{phone}@{d}" for d in sorted(set(GATEWAYS.values()))]
    key = (carrier or "").strip().lower().replace(" ", "").replace("-", "")
    if key not in GATEWAYS:
        raise ValueError(f"Unknown carrier '{carrier}'. Known: {', '.join(GATEWAYS)}")
    return [f"{phone}@{GATEWAYS[key]}"]


def build_email(to_addr, body):
    msg = EmailMessage()
    msg["From"] = f"{FROM_NAME} <{FROM_ADDR}>"
    msg["To"] = to_addr
    msg["Subject"] = ""               # empty subject; some gateways show it
    msg.set_content(body)
    return msg


def read_numbers(path):
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def main():
    rows = list(read_numbers(INPUT_CSV))
    print(f"Loaded {len(rows)} rows from {INPUT_CSV}")

    if DRY_RUN:
        for row in rows:
            phone = normalize_phone(row["phone"])
            for addr in gateway_addresses(phone, row.get("carrier")):
                print(f"  would send -> {addr}")
        print("Dry run complete. Set DRY_RUN = False to actually send.")
        return

    log = []
    context = ssl.create_default_context()

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASS)
        print("Logged in to SMTP.")

        for row in rows:
            phone = normalize_phone(row["phone"])
            body = MESSAGE.format(name=row.get("name", "there"))

            for addr in gateway_addresses(phone, row.get("carrier")):
                try:
                    server.send_message(build_email(addr, body))
                    print(f"  sent -> {addr}")
                    log.append((phone, row.get("carrier", ""), addr, "sent", ""))
                except Exception as e:
                    print(f"  FAILED -> {addr}: {e}")
                    log.append((phone, row.get("carrier", ""), addr, "failed", str(e)))

                time.sleep(SEND_DELAY)

    with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["phone", "carrier", "gateway", "status", "error"])
        w.writerows(log)

    print(f"Done. Results written to {LOG_CSV}")


if __name__ == "__main__":
    main()

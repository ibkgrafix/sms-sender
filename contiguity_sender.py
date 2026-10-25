#!/usr/bin/env python3
"""
Bulk SMS sender using Contiguity's API.
No A2P registration. Reads numbers from CSV, sends, logs results.

Note: posts to the raw API endpoint instead of client.text.send(),
because SDK 3.0.0's response decoder expects a 'metadata' field the
current API no longer returns. The raw call sidesteps that.
"""

import csv
import time
from contiguity import Contiguity

# ---------------- CONFIG ----------------
API_KEY = "contiguity_sk_3ac80c1eb8ed3daca87b7b5559befaa80bbc400b6fcef8944d81695a8ef19789"

MESSAGE = "Hello {name}! This is a test from our bulk SMS tool."
INPUT_CSV = "numbers.csv"
LOG_CSV = "results.csv"
DRY_RUN = False
SEND_DELAY = 0.2
# ----------------------------------------

client = Contiguity(token=API_KEY)


def normalize_phone(raw):
    digits = "".join(c for c in str(raw) if c.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits


def send_sms(phone, body):
    """POST straight to the API. Returns (message_id, delivery_status)."""
    r = client.client.post("/send/text", json={"to": phone, "message": body})
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text}")
    data = r.json()["data"]
    return data.get("message_id", ""), data.get("delivery", {}).get("status", "")


def read_numbers(path):
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def main():
    rows = list(read_numbers(INPUT_CSV))
    print(f"Loaded {len(rows)} rows from {INPUT_CSV}")

    if DRY_RUN:
        for row in rows:
            phone = normalize_phone(row["phone"])
            body = MESSAGE.format(name=row.get("name", "there"))
            print(f"  would send to {phone}: {body}")
        print("Dry run complete. Set DRY_RUN = False to send.")
        return

    log = []
    for row in rows:
        phone = normalize_phone(row["phone"])
        body = MESSAGE.format(name=row.get("name", "there"))
        try:
            msg_id, status = send_sms(phone, body)
            print(f"  sent -> {phone} ({status}, id={msg_id})")
            log.append((phone, "sent", status, msg_id, ""))
        except Exception as e:
            print(f"  FAILED -> {phone}: {e}")
            log.append((phone, "failed", "", "", str(e)))
        time.sleep(SEND_DELAY)

    with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["phone", "status", "delivery", "message_id", "error"])
        w.writerows(log)
    print(f"Done. Results written to {LOG_CSV}")


if __name__ == "__main__":
    main()
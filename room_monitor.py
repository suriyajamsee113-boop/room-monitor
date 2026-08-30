import json
import os
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("LINE_USER_ID")

TARGET_URL = "http://office.scphc.ac.th:8080/"
SEEN_FILE = "seen_bookings.json"

def send_line_message(text):
    if not CHANNEL_ACCESS_TOKEN or not USER_ID:
        print("[!] Missing LINE credentials")
        return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "to": USER_ID,
        "messages": [{"type": "text", "text": text}]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"[*] LINE status: {res.status_code}")
    except Exception as e:
        print(f"[!] Error sending LINE: {e}")

def load_seen_records():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen_records(records):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(records), f, ensure_ascii=False, indent=2)

def main():
    seen_records = load_seen_records()
    print(f"[*] Checking {TARGET_URL}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(TARGET_URL, timeout=30000)
        page.wait_for_timeout(3000)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")

        new_count = 0
        for row in rows:
            cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if not cols or len(cols) < 3:
                continue

            row_key = " | ".join(cols)
            
            # กรองเฉพาะรายการที่เป็นห้องประชุม และข้ามห้องสมุด
            is_meeting_room = "ห้องประชุม" in row_key
            is_library = "ห้องสมุด" in row_key or "library" in row_key.lower()

            if is_library or not is_meeting_room:
                continue

            if row_key not in seen_records:
                seen_records.add(row_key)
                new_count += 1
                details = "\n".join([f"• {c}" for c in cols if c and len(c) < 100][:6])
                msg = f"🔔 มีรายการจองห้องประชุมใหม่!\n------------------------\n{details}\n------------------------\n🌐 ดูรายละเอียด: {TARGET_URL}"
                send_line_message(msg)

        save_seen_records(seen_records)
        print(f"[*] Done. Found {new_count} new meeting room entries.")

if __name__ == "__main__":
    main()

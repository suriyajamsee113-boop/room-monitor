import json
import os
import re
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("LINE_USER_ID")

TARGET_URL = "http://office.scphc.ac.th:8080/"
SEEN_FILE = "seen_bookings.json"

def send_line_message(text):
    if not CHANNEL_ACCESS_TOKEN or not USER_ID:
        print("[!] ขาดข้อมูล LINE Token หรือ User ID")
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
        print(f"[*] สถานะการส่ง LINE: {res.status_code}")
        if res.status_code != 200:
            print(f"[!] LINE Response: {res.text}")
    except Exception as e:
        print(f"[!] ส่ง LINE ไม่สำเร็จ: {e}")

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
    print(f"[*] กำลังเปิดหน้าเว็บ {TARGET_URL}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(TARGET_URL, timeout=30000)
        page.wait_for_timeout(4000)

        soup = BeautifulSoup(page.content(), "html.parser")
        
        # ค้นหากล่องกิจกรรมทั้งหมดในปฏิทิน
        items = soup.find_all(["a", "div", "span"], class_=lambda c: c and any(x in str(c).lower() for x in ["event", "title", "cal"]))
        if not items:
            items = soup.find_all("a")

        valid_events = []
        for el in items:
            t = el.get_text(strip=True)
            if t and len(t) > 3 and not any(skip in t for skip in ["เข้าสู่ระบบ", "หน้าแรก", "ห้องสมุด", "Library"]):
                valid_events.append(t)

        valid_events = list(dict.fromkeys(valid_events))
        print(f"[*] ตรวจพบรายการในปฏิทิน: {len(valid_events)} รายการ")

        new_count = 0
        for text in valid_events:
            if text not in seen_records:
                seen_records.add(text)
                new_count += 1
                msg = (
                    f"🔔 รายการจองห้องประชุมใหม่\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📝 รายละเอียด: {text}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🌐 ตรวจสอบ: {TARGET_URL}"
                )
                print(f"[+] ยิงแจ้งเตือน -> {text[:30]}...")
                send_line_message(msg)

        save_seen_records(seen_records)
        browser.close()
        print(f"[*] เสร็จสิ้น (ส่งแจ้งเตือนสำเร็จ {new_count} รายการ)")

if __name__ == "__main__":
    main()

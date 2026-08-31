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
    print(f"[*] Opening {TARGET_URL}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(TARGET_URL, timeout=30000)
        page.wait_for_timeout(4000)

        # ค้นหาบล็อกรายการบนปฏิทินที่ระบุเวลาและชื่อกิจกรรม
        events = page.locator(".fc-event, .event, a[href*='view'], a[href*='detail'], a[onclick*='detail'], a[onclick*='view'], a.cal-event, td div[onclick]").all()
        
        # หากไม่เจอ class ปฏิทิน ให้ดึงลิงก์ทั้งหมดที่มีข้อความเวลาหรือตัวหนังสือ
        if not events:
            events = [el for el in page.locator("a, td[onclick]").all() if len(el.inner_text().strip()) > 3]

        print(f"[*] Identified event items to inspect: {len(events)}")

        new_count = 0

        for i, el in enumerate(events[:30]):  # ตรวจสอบรายการล่าสุด
            try:
                txt = el.inner_text().strip()
                if not txt:
                    continue

                # คลิกเปิดกล่องรายละเอียด
                el.click(timeout=2000, force=True)
                page.wait_for_timeout(1000)

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")

                # ตรวจหาตารางข้อมูลใน Popup
                tables = soup.find_all("table")
                data = {}
                for tbl in tables:
                    for tr in tbl.find_all("tr"):
                        tds = tr.find_all(["td", "th"])
                        if len(tds) >= 2:
                            k = tds[0].get_text(strip=True)
                            v = tds[1].get_text(strip=True)
                            data[k] = v

                room_name = data.get("ชื่อห้อง", "")
                topic = data.get("หัวข้อ", "")
                
                if room_name or "รายละเอียดของ การจอง" in html:
                    print(f"[{i}] Found Modal -> Room: '{room_name}' | Topic: '{topic}'")

                if "ห้องประชุม" in room_name:
                    building = data.get("อาคาร/สถานที่", "")
                    booker = data.get("ชื่อผู้จอง", "")
                    phone = data.get("โทรศัพท์", "")
                    datetime_str = data.get("วันที่", "")
                    dept = data.get("แผนกที่ขอใช้", "")
                    status = data.get("สถานะ", "")

                    unique_id = f"{room_name}_{topic}_{datetime_str}_{booker}"

                    if unique_id not in seen_records:
                        seen_records.add(unique_id)
                        new_count += 1
                        msg = (
                            f"🔔 มีรายการจองห้องประชุมใหม่!\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"📌 ห้อง: {room_name} ({building})\n"
                            f"📝 หัวข้อ: {topic}\n"
                            f"📅 วัน-เวลา: {datetime_str}\n"
                            f"👤 ผู้จอง: {booker} ({dept})\n"
                            f"📞 เบอร์โทร: {phone}\n"
                            f"📊 สถานะ: {status}\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"🌐 เข้าสู่ระบบ: {TARGET_URL}"
                        )
                        send_line_message(msg)

                # ปิด popup เพื่อเตรียมคลิกตัวถัดไป
                close_btn = page.locator(".modal button.close, .modal .close, button:has-text('ปิด'), button:has-text('Close'), .bootbox-close-button").first
                if close_btn.is_visible():
                    close_btn.click(timeout=1000)
                    page.wait_for_timeout(300)
                else:
                    page.keyboard.press("Escape")

            except Exception as ex:
                continue

        save_seen_records(seen_records)
        print(f"[*] Done. Processed {new_count} new meeting room bookings.")

if __name__ == "__main__":
    main()

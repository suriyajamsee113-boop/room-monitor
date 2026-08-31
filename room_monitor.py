import json
import os
import time
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
        page = browser.new_page()
        page.goto(TARGET_URL, timeout=30000)
        page.wait_for_timeout(4000)

        # ค้นหาบล็อกกิจกรรมทั้งหมดบนหน้าตาราง/ปฏิทิน
        # มองหา element ที่คลิกเปิด modal ได้ (ลิงก์/บล็อกสี/แถบเวลา)
        event_elements = page.query_selector_all("a, div[onclick], td[onclick], .fc-event, div[class*='event']")
        print(f"[*] Found candidate clickable items: {len(event_elements)}")

        new_count = 0

        for el in event_elements:
            try:
                txt = el.inner_text().strip()
                if not txt or len(txt) < 3:
                    continue

                # ลองคลิกที่บล็อกรายการเพื่อเปิดหน้าต่าง Popup
                el.click(timeout=1500)
                page.wait_for_timeout(1000)

                # ดึงเนื้อหาจาก Popup รายละเอียด
                modal = page.query_selector(".modal-content, .modal-body, div[class*='dialog'], div[class*='popup']")
                modal_html = modal.inner_html() if modal else page.content()

                if "รายละเอียดของ การจอง" in modal_html or "ชื่อห้อง" in modal_html:
                    soup = BeautifulSoup(modal_html, "html.parser")
                    
                    data = {}
                    for tr in soup.find_all("tr"):
                        tds = tr.find_all(["td", "th"])
                        if len(tds) >= 2:
                            k = tds[0].get_text(strip=True)
                            v = tds[1].get_text(strip=True)
                            data[k] = v

                    topic = data.get("หัวข้อ", "")
                    room_name = data.get("ชื่อห้อง", "")
                    building = data.get("อาคาร/สถานที่", "")
                    booker = data.get("ชื่อผู้จอง", "")
                    phone = data.get("โทรศัพท์", "")
                    datetime_str = data.get("วันที่", "")
                    dept = data.get("แผนกที่ขอใช้", "")
                    status = data.get("สถานะ", "")

                    # สร้าง Unique Key ป้องกันการแจ้งเตือนซ้ำ
                    unique_id = f"{room_name} | {topic} | {datetime_str} | {booker}"

                    # ตรวจสอบเงื่อนไขห้องประชุม
                    if "ห้องประชุม" in room_name and unique_id not in seen_records:
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

                    # กดปิด Modal (ถ้ามีปุ่มปิดกากบาท)
                    close_btn = page.query_selector("button.close, .close, span.close, [data-dismiss='modal']")
                    if close_btn:
                        close_btn.click(timeout=1000)
                        page.wait_for_timeout(500)
            except Exception:
                continue

        save_seen_records(seen_records)
        print(f"[*] Done. Processed {new_count} new meeting room bookings.")

if __name__ == "__main__":
    main()

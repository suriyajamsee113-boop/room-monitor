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
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception:
        pass

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

def check_rooms(playwright_instance=None):
    seen_records = load_seen_records()
    print(f"[*] [{time.strftime('%H:%M:%S')}] กำลังสแกนหน้าเว็บ...")

    def run_scan(p):
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        new_count = 0
        
        try:
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_timeout(4000)

            # 1. เจาะจงเฉพาะกล่องกิจกรรมรายใบ (fc-event)
            event_elements = page.locator(".fc-event, a.fc-day-grid-event, a.fc-time-grid-event").all()
            print(f"[*] พบกล่องการจองย่อยทั้งหมด: {len(event_elements)} รายการ")

            for el in event_elements:
                try:
                    # คลิกเปิด Popup รายละเอียด
                    el.click(timeout=1000, force=True)
                    page.wait_for_timeout(500)

                    soup = BeautifulSoup(page.content(), "html.parser")
                    
                    # ค้นหาตารางข้อมูลใน Modal Popup
                    data = {}
                    for tr in soup.find_all("tr"):
                        tds = tr.find_all(["td", "th"])
                        if len(tds) >= 2:
                            k = tds[0].get_text(strip=True)
                            v = tds[1].get_text(strip=True)
                            data[k] = v

                    room_name = data.get("ชื่อห้อง", "")
                    topic = data.get("หัวข้อ", "")
                    booker = data.get("ชื่อผู้จอง", "")
                    datetime_str = data.get("วันที่", "") or data.get("วันและเวลา", "")

                    # กรองเฉพาะรายการห้องประชุมที่มีข้อมูลครบถ้วน
                    if "ห้องประชุม" in room_name or (topic and datetime_str and not "ห้องสมุด" in room_name):
                        unique_id = f"{room_name}_{topic}_{datetime_str}_{booker}"

                        if unique_id not in seen_records:
                            seen_records.add(unique_id)
                            new_count += 1
                            
                            # ข้อความ 4 หัวข้อตามที่ต้องการ
                            msg = (
                                f"🔔 มีการจองห้องประชุมใหม่\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"1. หัวข้อ: {topic or '-'}\n"
                                f"2. ชื่อห้อง: {room_name or '-'}\n"
                                f"3. ชื่อผู้จอง: {booker or '-'}\n"
                                f"4. วันที่ เวลา: {datetime_str or '-'}\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"🌐 ระบบ: {TARGET_URL}"
                            )
                            send_line_message(msg)
                            print(f"[+] แจ้งเตือนรายการใหม่: {topic}")

                    # ปิด Popup
                    page.keyboard.press("Escape")
                except Exception:
                    continue

        finally:
            browser.close()

        save_seen_records(seen_records)
        print(f"[*] สแกนเสร็จสิ้น (ส่งแจ้งเตือน {new_count} รายการ)")

    if playwright_instance:
        run_scan(playwright_instance)
    else:
        with sync_playwright() as p:
            run_scan(p)

if __name__ == "__main__":
    check_rooms()

import json
import os
import re
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
        print("[!] Missing LINE Token / User ID")
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
        if res.status_code != 200:
            print(f"[!] Response: {res.text}")
    except Exception as e:
        print(f"[!] Send error: {e}")

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

def extract_details(text):
    """แยก 4 หัวข้อจากข้อความในกล่องกิจกรรมหรือ Popup"""
    # 1. เวลา
    time_match = re.search(r"(\d{1,2}:\d{2}\s*(?:น\.)?(?:\s*-\s*\d{1,2}:\d{2}\s*(?:น\.)?)?)", text)
    time_str = time_match.group(1) if time_match else "-"

    # 2. ชื่อห้อง
    room_match = re.search(r"(ห้องประชุม[^\s\n\r,]+|ห้อง[^\s\n\r,]+)", text)
    room_name = room_match.group(1) if room_match else "ห้องประชุม"

    # 3. ผู้จอง
    booker_match = re.search(r"(?:ผู้จอง|โดย|ชื่อผู้จอง)[:\s]+([^\n\r,]+)", text)
    booker = booker_match.group(1).strip() if booker_match else "-"

    # 4. หัวข้อ (ตัดส่วนเวลาและห้องออกเพื่อเป็นหัวข้อ)
    clean_topic = re.sub(r"\d{1,2}:\d{2}", "", text)
    clean_topic = re.sub(r"ห้องประชุม[^\s]+", "", clean_topic).strip()
    topic = clean_topic if len(clean_topic) > 2 else text

    return topic, room_name, booker, time_str

def main():
    seen_records = load_seen_records()
    print(f"[*] [{time.strftime('%H:%M:%S')}] กำลังเปิดหน้าเว็บ...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto(TARGET_URL, timeout=30000)
            page.wait_for_timeout(4000)

            # ค้นหากล่องกิจกรรมทั้งหมดในปฏิทิน
            events = page.locator(".fc-event, a.fc-event, div.fc-content, a[href*='booking'], a[onclick*='view']").all()
            print(f"[*] เจอกล่องกิจกรรม: {len(events)} กล่อง")

            new_count = 0
            for idx, ev in enumerate(events):
                raw_text = ev.inner_text().strip()
                if not raw_text or len(raw_text) < 3 or "ห้องสมุด" in raw_text:
                    continue

                # พยายามคลิกเพื่อดึงข้อความเพิ่มเติมจาก Popup (ถ้ามี)
                popup_text = ""
                try:
                    ev.click(timeout=800, force=True)
                    page.wait_for_timeout(400)
                    soup = BeautifulSoup(page.content(), "html.parser")
                    modal = soup.find(class_=re.compile(r"modal|popup|dialog|detail", re.I))
                    if modal:
                        popup_text = modal.get_text(separator=" ", strip=True)
                    page.keyboard.press("Escape")
                except Exception:
                    pass

                full_info = popup_text if len(popup_text) > len(raw_text) else raw_text
                topic, room_name, booker, datetime_str = extract_details(full_info)

                unique_key = f"{topic}_{datetime_str}_{room_name}"

                if unique_key not in seen_records:
                    seen_records.add(unique_key)
                    new_count += 1

                    msg = (
                        f"🔔 รายการจองห้องประชุมใหม่\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"1. หัวข้อ: {topic}\n"
                        f"2. ชื่อห้อง: {room_name}\n"
                        f"3. ชื่อผู้จอง: {booker}\n"
                        f"4. วันที่ เวลา: {datetime_str}\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🌐 ดูระบบ: {TARGET_URL}"
                    )
                    print(f"[+] ตรวจพบรายการใหม่: {topic}")
                    send_line_message(msg)

            save_seen_records(seen_records)
            print(f"[*] รอบนี้ส่งแจ้งเตือนสำเร็จ: {new_count} รายการ")

        except Exception as e:
            print(f"[!] ผิดพลาด: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    main()

import json
import os
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("LINE_USER_ID")
DEBUG = os.environ.get("DEBUG", "0") == "1"  # ตั้ง DEBUG=1 ตอนรันเพื่อเก็บ screenshot/html ตัวอย่าง

TARGET_URL = "http://office.scphc.ac.th:8080/"
SEEN_FILE = "seen_bookings.json"
DEBUG_DIR = "debug_output"


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


def extract_booking_data(html):
    """แกะข้อมูลจาก HTML (ของ main page หรือของ frame ก็ได้) ถ้าเจอตาราง 'ชื่อห้อง' คืนค่า dict, ไม่งั้นคืน None"""
    if "ชื่อห้อง" not in html and "รายละเอียดของ การจอง" not in html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    data = {}
    for tr in soup.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if len(tds) >= 2:
            data[tds[0].get_text(strip=True)] = tds[1].get_text(strip=True)
    return data if data else None


def main():
    seen_records = load_seen_records()
    print(f"[*] Opening {TARGET_URL}...")

    if DEBUG and not os.path.exists(DEBUG_DIR):
        os.makedirs(DEBUG_DIR)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # กัน alert()/confirm()/prompt() ค้างรอ ซึ่งเป็นสาเหตุหลักที่ทำให้สคริปต์รันช้ามาก
        page.on("dialog", lambda dialog: dialog.dismiss())

        page.goto(TARGET_URL, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        print(f"[*] Frames on page: {len(page.frames)}")
        for fr in page.frames:
            print(f"    - frame url: {fr.url}")

        items = page.locator("a, div[onclick], td[onclick], div[class*='event']").all()
        print(f"[*] Total candidates found: {len(items)}")

        new_count = 0
        checked_count = 0

        for idx, item in enumerate(items):
            try:
                txt = item.inner_text().strip()
                if not txt or len(txt) < 3 or "ห้องสมุด" in txt:
                    continue

                item.click(timeout=1000, force=True)
                page.wait_for_timeout(400)

                # ตรวจทั้ง main page และทุก frame ย่อย เผื่อ popup แสดงผลอยู่ใน iframe
                data = None
                html_sources = [("main", page.content())]
                for fr in page.frames:
                    try:
                        html_sources.append((fr.url, fr.content()))
                    except Exception:
                        pass

                for source_name, html in html_sources:
                    parsed = extract_booking_data(html)
                    if parsed:
                        data = parsed
                        break

                if DEBUG and checked_count < 5:
                    page.screenshot(path=f"{DEBUG_DIR}/click_{idx}.png")
                    with open(f"{DEBUG_DIR}/click_{idx}.html", "w", encoding="utf-8") as f:
                        f.write(page.content())
                    checked_count += 1

                if data:
                    room_name = data.get("ชื่อห้อง", "")
                    topic = data.get("หัวข้อ", "")
                    booker = data.get("ชื่อผู้จอง", "")
                    datetime_str = data.get("วันที่", "")

                    if "ห้องประชุม" in room_name:
                        unique_id = f"{room_name}_{topic}_{datetime_str}_{booker}"
                        if unique_id not in seen_records:
                            seen_records.add(unique_id)
                            new_count += 1
                            msg = (
                                f"🔔 รายการจองห้องประชุมใหม่\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"1. หัวข้อ: {topic}\n"
                                f"2. ชื่อห้อง: {room_name}\n"
                                f"3. ชื่อผู้จอง: {booker}\n"
                                f"4. วันที่ เวลา: {datetime_str}\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"🌐 ดูรายละเอียด: {TARGET_URL}"
                            )
                            send_line_message(msg)

                page.keyboard.press("Escape")
            except Exception as e:
                if DEBUG:
                    print(f"[debug] item {idx} error: {e}")
                continue

        save_seen_records(seen_records)
        print(f"[*] Done. Processed {new_count} new entries.")


if __name__ == "__main__":
    main()

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
    print(f"[*] Opening {TARGET_URL}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(TARGET_URL, timeout=30000)
        page.wait_for_timeout(5000)

        # รวมค้นหาทั้งในหน้าหลัก และทุก Frame/iFrame
        frames_to_check = [page] + page.frames

        print(f"[*] Total frames/pages to scan: {len(frames_to_check)}")

        new_count = 0

        for frame_idx, frame in enumerate(frames_to_check):
            # ค้นหาตัวที่คลิกได้ทั้งหมดในแต่ละ frame
            candidates = frame.locator("a, div[onclick], td[onclick], div[class*='event'], span[onclick]").all()
            
            valid_items = []
            for item in candidates:
                try:
                    txt = item.inner_text().strip()
                    if txt and len(txt) > 2 and ("ห้อง" in txt or ":" in txt or " " in txt):
                        valid_items.append((item, txt))
                except Exception:
                    continue

            if valid_items:
                print(f"[*] Frame {frame_idx} found {len(valid_items)} event candidates.")

            for el, txt in valid_items[:20]:
                try:
                    el.click(timeout=1500, force=True)
                    page.wait_for_timeout(800)

                    soup = BeautifulSoup(page.content(), "html.parser")
                    # ค้นหาใน frame ด้วยเผื่อ popup อยู่ข้างใน
                    for f in page.frames:
                        try:
                            soup_f = BeautifulSoup(f.content(), "html.parser")
                            if "รายละเอียดของ การจอง" in f.content() or "ชื่อห้อง" in f.content():
                                soup = soup_f
                                break
                        except Exception:
                            pass

                    data = {}
                    for tr in soup.find_all("tr"):
                        tds = tr.find_all(["td", "th"])
                        if len(tds) >= 2:
                            data[tds[0].get_text(strip=True)] = tds[1].get_text(strip=True)

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
                except Exception:
                    continue

        save_seen_records(seen_records)
        print(f"[*] Done. Processed {new_count} new entries.")

if __name__ == "__main__":
    main()

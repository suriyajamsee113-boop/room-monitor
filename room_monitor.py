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
    print(f"[*] Opening {TARGET_URL} with Headless Browser...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(TARGET_URL, timeout=30000)
        # รอให้ปฏิทินเรนเดอร์กล่องกิจกรรม
        page.wait_for_timeout(4000)

        # 1. ลองดึงข้อมูลกิจกรรมทั้งหมดที่ FullCalendar เก็บไว้ใน Memory โดยตรง (เร็วมาก)
        events_data = page.evaluate("""() => {
            try {
                if (window.$ && $.fn && $.fn.fullCalendar) {
                    var clientEvents = $('.calendar, #calendar, [id*="calendar"]').fullCalendar('clientEvents');
                    if (clientEvents && clientEvents.length > 0) {
                        return clientEvents.map(e => ({
                            id: e.id || '',
                            title: e.title || '',
                            start: e.start ? e.start.format() : '',
                            end: e.end ? e.end.format() : '',
                            description: e.description || '',
                            location: e.location || '',
                            room: e.room || ''
                        }));
                    }
                }
            } catch(err) {}
            return [];
        }""")

        new_count = 0

        # หากดึงจาก FullCalendar Memory ได้
        if events_data:
            print(f"[*] Extracted {len(events_data)} events from calendar memory directly.")
            for ev in events_data:
                full_text = f"{ev.get('title')} {ev.get('description')} {ev.get('location')} {ev.get('room')}"
                if "ห้องสมุด" in full_text or "library" in full_text.lower():
                    continue

                ev_id = str(ev.get("id") or f"{ev.get('title')}_{ev.get('start')}")
                if ev_id not in seen_records:
                    seen_records.add(ev_id)
                    new_count += 1
                    msg = (
                        f"🔔 รายการจองห้องประชุมใหม่\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"1. หัวข้อ: {ev.get('title')}\n"
                        f"2. ชื่อห้อง: {ev.get('room') or ev.get('location') or 'ห้องประชุม'}\n"
                        f"3. ชื่อผู้จอง: {ev.get('description') or '-'}\n"
                        f"4. วันที่ เวลา: {ev.get('start')}\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🌐 ดูรายละเอียด: {TARGET_URL}"
                    )
                    send_line_message(msg)

        # 2. หากดึงจาก memory ไม่ได้ ให้ดึงจาก HTML elements ที่เรนเดอร์บนหน้าจอ
        else:
            print("[*] Fallback: Reading rendered DOM elements...")
            event_nodes = page.locator(".fc-event, .fc-content, a.cal-event, tr.event-row").all()
            print(f"[*] Found {len(event_nodes)} visible events on page.")

            for i, node in enumerate(event_nodes[:15]):
                try:
                    node.click(timeout=1500)
                    page.wait_for_timeout(600)

                    soup = BeautifulSoup(page.content(), "html.parser")
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

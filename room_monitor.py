import json
import os
import re
import requests
from bs4 import BeautifulSoup

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("LINE_USER_ID")

BASE_URL = "http://office.scphc.ac.th:8080"
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
    print(f"[*] Checking {BASE_URL}...")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    try:
        res = session.get(BASE_URL, timeout=15)
        html = res.text
    except Exception as e:
        print(f"[!] Cannot connect to website: {e}")
        return

    # 1. ค้นหา Endpoint ดึง Event ของปฏิทินที่ซ่อนอยู่ในหน้าเว็บ
    # เช่น events.php, get_events.php, data.php หรือ url ใน fullcalendar
    event_urls = re.findall(r"['\"]([^'\"]*(?:event|booking|load|data|calendar)[^'\"]*\.php[^'\"]*)['\"]", html, re.I)
    
    print(f"[*] Discovered calendar endpoints: {event_urls}")

    # 2. ค้นหา ID หรือรหัสการจองทั้งหมดในหน้าเว็บ
    booking_ids = re.findall(r"(?:id|booking_id|book_id)=(\d+)", html, re.I)
    booking_ids += re.findall(r"detail[^\d]*(\d+)", html, re.I)
    booking_ids = list(set(booking_ids))
    print(f"[*] Discovered booking IDs directly: {len(booking_ids)}")

    # 3. ลองดึงข้อมูลรายละเอียดจาก ID ที่พบ
    new_count = 0
    for bid in booking_ids[:30]:
        check_urls = [
            f"{BASE_URL}/detail.php?id={bid}",
            f"{BASE_URL}/view.php?id={bid}",
            f"{BASE_URL}/booking_detail.php?id={bid}",
            f"{BASE_URL}/?id={bid}"
        ]
        for url in check_urls:
            try:
                r = session.get(url, timeout=5)
                if "รายละเอียดของ การจอง" in r.text or "ชื่อห้อง" in r.text:
                    soup = BeautifulSoup(r.text, "html.parser")
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
                    datetime_str = data.get("วันที่", "")

                    if "ห้องประชุม" in room_name:
                        unique_id = f"{bid}_{room_name}_{datetime_str}"
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
                                f"🌐 ดูรายละเอียด: {url}"
                            )
                            send_line_message(msg)
                    break
            except Exception:
                continue

    save_seen_records(seen_records)
    print(f"[*] Finished check. Sent {new_count} notifications.")

if __name__ == "__main__":
    main()

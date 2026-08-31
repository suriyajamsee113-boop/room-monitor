import json
import os
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
    print(f"[*] Fetching page from {BASE_URL}...")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    try:
        res = session.get(BASE_URL, timeout=15)
        html = res.text
    except Exception as e:
        print(f"[!] Failed to connect: {e}")
        return

    soup = BeautifulSoup(html, "html.parser")
    
    detail_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(keyword in href.lower() for keyword in ["detail", "view", "booking", "id="]):
            full_url = href if href.startswith("http") else f"{BASE_URL}/{href.lstrip('/')}"
            if full_url not in detail_links:
                detail_links.append(full_url)

    print(f"[*] Found {len(detail_links)} detail links to check.")

    new_count = 0
    for link in detail_links[:20]:
        try:
            r = session.get(link, timeout=10)
            sub_soup = BeautifulSoup(r.text, "html.parser")
            
            data = {}
            for tr in sub_soup.find_all("tr"):
                tds = tr.find_all(["td", "th"])
                if len(tds) >= 2:
                    k = tds[0].get_text(strip=True)
                    v = tds[1].get_text(strip=True)
                    data[k] = v

            room_name = data.get("ชื่อห้อง", "")
            topic = data.get("หัวข้อ", "")

            # กรองเฉพาะรายการห้องประชุม
            if "ห้องประชุม" in room_name or "ห้องประชุม" in r.text:
                booker = data.get("ชื่อผู้จอง", "")
                datetime_str = data.get("วันที่", "")

                unique_id = f"{room_name}_{topic}_{datetime_str}_{booker}"

                if unique_id not in seen_records:
                    seen_records.add(unique_id)
                    new_count += 1
                    
                    # รูปแบบข้อความแสดง 4 รายละเอียดตามที่ต้องการ
                    msg = (
                        f"🔔 รายการจองห้องประชุมใหม่\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"1. หัวข้อ: {topic}\n"
                        f"2. ชื่อห้อง: {room_name}\n"
                        f"3. ชื่อผู้จอง: {booker}\n"
                        f"4. วันที่ เวลา: {datetime_str}\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🌐 ดูรายละเอียด: {link}"
                    )
                    send_line_message(msg)
        except Exception:
            continue

    save_seen_records(seen_records)
    print(f"[*] Finished. Found {new_count} new bookings.")

if __name__ == "__main__":
    main()

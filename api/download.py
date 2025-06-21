import os
import shutil
import tempfile
import asyncio
import requests
import re
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from urllib.parse import urlencode, urlparse, parse_qs

app = FastAPI()

COOKIE = "ndus=Y2f2tB1peHuigEgX5NpHQFeiY88k9XMojvuvxNVb"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/135.0.0.0 Safari/537.36",
    "Cookie": COOKIE,
}

DL_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Referer": "https://www.terabox.com/",
    "Connection": "keep-alive",
    "Cookie": COOKIE,
}

def get_size(bytes_len: int) -> str:
    if bytes_len >= 1024**3:
        return f"{bytes_len / 1024**3:.2f} GB"
    if bytes_len >= 1024**2:
        return f"{bytes_len / 1024**2:.2f} MB"
    if bytes_len >= 1024:
        return f"{bytes_len / 1024:.2f} KB"
    return f"{bytes_len} bytes"

def extract_token(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else None

def get_real_download_url(dlink: str) -> str:
    response = requests.get(dlink, headers=DL_HEADERS, allow_redirects=False)
    if response.status_code in [302, 301] and "Location" in response.headers:
        return response.headers["Location"]
    raise ValueError("Failed to resolve real download URL from dlink.")

def get_file_info(share_url: str) -> dict:
    resp = requests.get(share_url, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        raise ValueError(f"Failed to fetch share page ({resp.status_code})")

    final_url = resp.url
    parsed = urlparse(final_url)
    surl = parse_qs(parsed.query).get("surl", [None])[0]
    if not surl:
        raise ValueError("Invalid URL: 'surl' not found.")

    html = requests.get(final_url, headers=HEADERS).text
    thumb_url = extract_token(r'<meta property="og:image" content="([^"]+)"', html)

    js_token = extract_token(r'fn%28%22([A-F0-9]{64,})%22%29', html)
    logid = extract_token(r'dp-logid=([a-zA-Z0-9]+)&', html)
    bdstoken = extract_token(r'"bdstoken":"([^"]+)"', html)  # <-- added

    if not js_token or not logid:
        print("⚠️ js_token:", js_token)
        print("⚠️ logid:", logid)
        print("⚠️ bdstoken:", bdstoken)  # optional debug
        print("⚠️ HTML:", html[:2000])
        raise ValueError("Failed to extract authentication tokens. Check HTML format.")

    params = {
        "app_id": "250528", "web": "1", "channel": "dubox",
        "clienttype": "0", "jsToken": js_token, "dp-logid": logid,
        "page": "1", "num": "20", "by": "name", "order": "asc",
        "site_referer": final_url, "shorturl": surl, "root": "1,"
    }

    info = requests.get(
        "https://www.terabox.app/share/list?" + urlencode(params),
        headers=HEADERS
    ).json()

    if info.get("errno") or not info.get("list"):
        raise ValueError(f"API Error: {info.get('errmsg', 'Unknown error')}")

    file = info["list"][0]
    raw_dlink = file.get("dlink", "")
    real_dlink = get_real_download_url(raw_dlink)
    size = int(file.get("size", 0))

    return {
        "name": file.get("server_filename", "file"),
        "download_link": real_dlink,
        "size_bytes": size,
        "size_str": get_size(size),
        "thumbnail": thumb_url,
        "bdstoken": bdstoken  # included in return dict (in case needed later)
    }

async def send_photo_message(bot_token: str, chat_id: str, photo: str, caption: str):
    await asyncio.to_thread(requests.post,
        f"https://api.telegram.org/bot{bot_token}/sendPhoto",
        json={
            "chat_id": chat_id,
            "photo": photo,
            "caption": caption,
            "parse_mode": "Markdown"
        }
    )

async def send_telegram_message(bot_token: str, chat_id: str, text: str):
    await asyncio.to_thread(requests.post,
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
    )

@app.post("/api/download")
async def download_handler(request: Request):
    temp_file = None
    try:
        payload = await request.json()
        chat_id = payload.get("chat_id")
        link = payload.get("link")
        bot_token = payload.get("bot_token")

        if not all([chat_id, link, bot_token]):
            return JSONResponse(status_code=400, content={"error": "Missing required fields."})

        info = get_file_info(link)

        if info.get("thumbnail"):
            await send_photo_message(
                bot_token, chat_id, info["thumbnail"],
                f"📩 *Link received!*\n⏳ Processing...\n🔗 [TeraBox Link]({link})"
            )
        else:
            await send_telegram_message(
                bot_token, chat_id,
                f"📩 *Link received!*\n⏳ Processing...\n🔗 [TeraBox Link]({link})"
            )

        await send_telegram_message(
            bot_token, chat_id,
            f"⏳ *Downloading...*\n📄 *{info['name']}*\n💾 *{info['size_str']}*"
        )

        temp_file = os.path.join(tempfile.gettempdir(), info["name"])
        with requests.get(info["download_link"], headers=DL_HEADERS, stream=True) as r:
            r.raise_for_status()
            with open(temp_file, "wb") as f:
                shutil.copyfileobj(r.raw, f)

        with open(temp_file, "rb") as f:
            files = {"document": (info["name"], f)}
            data = {
                "chat_id": chat_id,
                "caption": f"📄 {info['name']}\n💾 {info['size_str']}\n🔗 {link}"
            }
            send_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
            requests.post(send_url, files=files, data=data)

        return {"status": "success", "message": "File sent to Telegram"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass

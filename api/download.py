# api/download.py
# Backend for Terabox Downloader Bot
# Credits: https://github.com/MN-BOTS
# @MrMNTG @MusammilN

import os
import tempfile
import shutil
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from urllib.parse import urlencode, urlparse, parse_qs

app = FastAPI()

# Replace with your actual working Terabox cookie
COOKIE = "ndus=Y2f2tB1peHuigEgX5NpHQFeiY88k9XMojvuvxNVb"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    "Connection": "keep-alive",
    "DNT": "1",
    "Host": "www.terabox.app",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0",
    "sec-ch-ua": '"Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cookie": COOKIE,
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

DL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.terabox.com/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cookie": COOKIE,
}

def get_size(bytes_len: int) -> str:
    if bytes_len >= 1024 ** 3:
        return f"{bytes_len / 1024**3:.2f} GB"
    if bytes_len >= 1024 ** 2:
        return f"{bytes_len / 1024**2:.2f} MB"
    if bytes_len >= 1024:
        return f"{bytes_len / 1024:.2f} KB"
    return f"{bytes_len} bytes"

def find_between(text: str, start: str, end: str) -> str:
    try:
        return text.split(start, 1)[1].split(end, 1)[0]
    except Exception:
        return ""

def get_file_info(share_url: str) -> dict:
    resp = requests.get(share_url, headers=HEADERS, allow_redirects=True)
    if resp.status_code != 200:
        raise ValueError(f"Failed to fetch share page ({resp.status_code})")
    final_url = resp.url

    parsed = urlparse(final_url)
    surl = parse_qs(parsed.query).get("surl", [None])[0]
    if not surl:
        raise ValueError("Invalid share URL (missing surl)")

    page = requests.get(final_url, headers=HEADERS)
    html = page.text

    js_token = find_between(html, 'fn%28%22', '%22%29')
    logid = find_between(html, 'dp-logid=', '&')
    bdstoken = find_between(html, 'bdstoken":"', '"')
    if not all([js_token, logid, bdstoken]):
        raise ValueError("Failed to extract authentication tokens")

    params = {
        "app_id": "250528", "web": "1", "channel": "dubox",
        "clienttype": "0", "jsToken": js_token, "dp-logid": logid,
        "page": "1", "num": "20", "by": "name", "order": "asc",
        "site_referer": final_url, "shorturl": surl, "root": "1,",
    }

    info = requests.get(
        "https://www.terabox.app/share/list?" + urlencode(params),
        headers=HEADERS
    ).json()

    if info.get("errno") or not info.get("list"):
        errmsg = info.get("errmsg", "Unknown error")
        raise ValueError(f"List API error: {errmsg}")

    file = info["list"][0]
    size_bytes = int(file.get("size", 0))
    return {
        "name": file.get("server_filename", "download"),
        "download_link": file.get("dlink", ""),
        "size_bytes": size_bytes,
        "size_str": get_size(size_bytes)
    }

@app.post("/api/download")
async def download_handler(request: Request):
    try:
        data = await request.json()
        chat_id = data.get("chat_id")
        link = data.get("link")
        bot_token = data.get("bot_token")

        if not chat_id or not link or not bot_token:
            return JSONResponse(status_code=400, content={"error": "Missing required parameters."})

        info = get_file_info(link)
        temp_path = os.path.join(tempfile.gettempdir(), info["name"])

        # Download the file
        with requests.get(info["download_link"], headers=DL_HEADERS, stream=True) as r:
            r.raise_for_status()
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(r.raw, f)

        # Upload to Telegram
        send_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        with open(temp_path, "rb") as doc_file:
            files = {"document": (info["name"], doc_file)}
            data = {
                "chat_id": chat_id,
                "caption": f"📄 {info['name']}\n📦 {info['size_str']}\n🔗 {link}"
            }
            res = requests.post(send_url, files=files, data=data)
            res.raise_for_status()

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed: {e}"})

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return {"status": "success", "message": "File sent to Telegram"}

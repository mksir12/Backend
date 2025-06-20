# api/download.py
import os
import json
import requests
from urllib.parse import urlencode, urlparse, parse_qs
from flask import Flask, request

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Cookie": os.getenv("TERABOX_COOKIE") or "ndus=your_cookie_here"
}

DL_HEADERS = HEADERS.copy()
DL_HEADERS["Referer"] = "https://www.terabox.com/"

def get_size(bytes_len: int) -> str:
    if bytes_len >= 1024 ** 3:
        return f"{bytes_len / 1024**3:.2f} GB"
    if bytes_len >= 1024 ** 2:
        return f"{bytes_len / 1024**2:.2f} MB"
    if bytes_len >= 1024:
        return f"{bytes_len / 1024:.2f} KB"
    return f"{bytes_len} bytes"

def extract_between(text, start, end):
    try:
        return text.split(start, 1)[1].split(end, 1)[0]
    except:
        return ""

def get_file_info(link):
    session = requests.Session()
    page = session.get(link, headers=HEADERS)
    final_url = page.url

    parsed = urlparse(final_url)
    surl = parse_qs(parsed.query).get("surl", [None])[0]
    if not surl:
        raise Exception("Invalid Terabox URL")

    js_token = extract_between(page.text, 'fn%28%22', '%22%29')
    logid = extract_between(page.text, 'dp-logid=', '&')
    bdstoken = extract_between(page.text, 'bdstoken":"', '"')

    if not all([js_token, logid, bdstoken]):
        raise Exception("Missing tokens")

    params = {
        "app_id": "250528", "web": "1", "channel": "dubox",
        "clienttype": "0", "jsToken": js_token, "dp-logid": logid,
        "page": "1", "num": "20", "by": "name", "order": "asc",
        "site_referer": final_url, "shorturl": surl, "root": "1,"
    }

    info = session.get("https://www.terabox.app/share/list?" + urlencode(params), headers=HEADERS).json()
    file = info["list"][0]
    return {
        "name": file.get("server_filename", "file"),
        "size": int(file.get("size", 0)),
        "link": file.get("dlink", "")
    }

@app.route("/api/download", methods=["POST"])
def download_handler():
    data = request.json
    chat_id = data.get("chat_id")
    terabox_link = data.get("link")
    bot_token = data.get("bot_token")

    if not chat_id or not terabox_link or not bot_token:
        return "Missing data", 400

    try:
        file_info = get_file_info(terabox_link)
        file_name = file_info["name"]
        file_size = get_size(file_info["size"])

        file_data = requests.get(file_info["link"], headers=DL_HEADERS)
        tg_api = f"https://api.telegram.org/bot{bot_token}/sendDocument"

        files = {
            "document": (file_name, file_data.content)
        }
        data = {
            "chat_id": chat_id,
            "caption": f"📄 {file_name}\n💾 {file_size}\n🔗 {terabox_link}"
        }

        requests.post(tg_api, data=data, files=files)
        return "OK", 200

    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": error_msg}
        )
        return "Failed", 500

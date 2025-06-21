import os
import shutil
import tempfile
import asyncio
import time
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

def get_size(bytes_len: int) -> str:
    if bytes_len >= 1024**3:
        return f"{bytes_len / 1024**3:.2f} GB"
    if bytes_len >= 1024**2:
        return f"{bytes_len / 1024**2:.2f} MB"
    if bytes_len >= 1024:
        return f"{bytes_len / 1024:.2f} KB"
    return f"{bytes_len} bytes"

def get_file_info(share_url: str) -> dict:
    api_url = f"https://teraboxvideodl.pages.dev/api/?url={share_url}&server=1"
    resp = requests.get(api_url)
    data = resp.json()
    if "download_url" not in data:
        raise ValueError("Invalid API response: no download_url")
    size_bytes = int(data.get("size", 0))
    return {
        "name": data.get("name", "file.mp4"),
        "download_link": data["download_url"],
        "size_bytes": size_bytes,
        "size_str": get_size(size_bytes),
        "thumbnail": data.get("image")
    }

async def send_photo(bot_token: str, chat_id: str, photo: str, caption: str):
    await asyncio.to_thread(requests.post,
        f"https://api.telegram.org/bot{bot_token}/sendPhoto",
        json={"chat_id": chat_id, "photo": photo, "caption": caption, "parse_mode": "Markdown"}
    )

async def send_message(bot_token: str, chat_id: str, text: str):
    await asyncio.to_thread(requests.post,
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    )

async def download_with_progress(url, dest_path, total_size, bot_token, chat_id, file_name):
    response = requests.get(url, stream=True)
    response.raise_for_status()
    chunk_size = 8192
    downloaded = 0
    start = time.time()
    last = 0
    message_id = None

    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if not chunk:
                continue
            f.write(chunk)
            downloaded += len(chunk)
            now = time.time()
            if now - last < 2:
                continue
            last = now
            elapsed = now - start
            speed = downloaded / elapsed if elapsed else 0
            percent = (downloaded / total_size) * 100
            eta = int((total_size - downloaded) / speed) if speed else 0
            bar = "█" * int(percent // 10) + " " * (10 - int(percent // 10))
            text = (
    f"⬇️ **Downloading:** *{file_name}*\n\n"
    f"🔴 `{bar}` **{percent:.1f}%**\n"
    f"💾 **{get_size(downloaded)} / {get_size(total_size)}**\n\n"
    f"⚡ **Speed:** `{get_size(int(speed))}/s`\n"
    f"⏱️ **ETA:** `{eta}s`\n"
    f"👤 **User:** *User*"
)
payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
            if message_id is None:
                resp = requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json=payload)
                message_id = resp.json().get("result", {}).get("message_id")
            else:
                payload["message_id"] = message_id
                requests.post(f"https://api.telegram.org/bot{bot_token}/editMessageText", json=payload)

    return message_id

@app.post("/api/download")
async def download_handler(request: Request):
    temp_file = None
    try:
        payload = await request.json()
        chat_id = payload.get("chat_id")
        link = payload.get("link")
        bot_token = payload.get("bot_token")
        if not all([chat_id, link, bot_token]):
            return JSONResponse(status_code=400, content={"error": "Missing fields."})

        info = get_file_info(link)

        if info["thumbnail"]:
            await send_photo(bot_token, chat_id, info["thumbnail"],
                             f"📩 *Link received!*\n⏳ Processing...\n🔗 [TeraBox Link]({link})")
        else:
            await send_message(bot_token, chat_id,
                               f"📩 *Link received!*\n⏳ Processing...\n🔗 [TeraBox Link]({link})")

        temp_file = os.path.join(tempfile.gettempdir(), info["name"])
        progress_msg_id = await download_with_progress(info["download_link"], temp_file,
                                                       info["size_bytes"], bot_token, chat_id, info["name"])

        with open(temp_file, "rb") as f:
            files = {"document": (info["name"], f)}
            data = {"chat_id": chat_id,
                    "caption": f"📄 {info['name']}\n💾 {info['size_str']}\n🔗 {link}"}
            requests.post(f"https://api.telegram.org/bot{bot_token}/sendDocument", files=files, data=data)

        if progress_msg_id:
            requests.post(f"https://api.telegram.org/bot{bot_token}/deleteMessage",
                          json={"chat_id": chat_id, "message_id": progress_msg_id})

        return {"status": "success"}

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

    finally:
        if temp_file and os.path.exists(temp_file):
            try: os.remove(temp_file)
            except: pass

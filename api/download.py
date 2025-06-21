import os
import shutil
import tempfile
import asyncio
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
    api_url = f"https://teraboxvideodl.pages.dev/api/?url={share_url}&server=2"
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

def download_file(url: str, dest_path: str):
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(response.raw, f)

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

        message = (
            f"📩 *Link received!*\n"
            f"⏳ Processing...\n"
            f"🔗 [TeraBox Link]({link})"
        )

        if info["thumbnail"]:
            await send_photo(bot_token, chat_id, info["thumbnail"], message)
        else:
            await send_message(bot_token, chat_id, message)

        temp_file = os.path.join(tempfile.gettempdir(), info["name"])
        download_file(info["download_link"], temp_file)

        with open(temp_file, "rb") as f:
            files = {"document": (info["name"], f)}
            data = {
                "chat_id": chat_id,
                "caption": f"📄 {info['name']}\n💾 {info['size_str']}\n🔗 {link}"
            }
            requests.post(f"https://api.telegram.org/bot{bot_token}/sendDocument", files=files, data=data)

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

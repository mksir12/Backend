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
    for server in [2, 3, 1]:
        api_url = f"https://teraboxvideodl.pages.dev/api/?url={share_url}&server={server}"
        resp = requests.get(api_url)
        data = resp.json()
        if "download_url" in data:
            size_bytes = int(data.get("size", 0))
            return {
                "name": data.get("name", "file.mp4"),
                "download_link": data["download_url"],
                "size_bytes": size_bytes,
                "size_str": get_size(size_bytes),
                "thumbnail": data.get("image")
            }
    raise ValueError("Invalid API response: no download_url from all servers")

async def send_photo(bot_token: str, chat_id: str, photo: str, caption: str) -> int:
    response = await asyncio.to_thread(requests.post,
        f"https://api.telegram.org/bot{bot_token}/sendPhoto",
        json={"chat_id": chat_id, "photo": photo, "caption": caption, "parse_mode": "Markdown"}
    )
    return response.json().get("result", {}).get("message_id")

async def send_message(bot_token: str, chat_id: str, text: str) -> int:
    response = await asyncio.to_thread(requests.post,
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    )
    return response.json().get("result", {}).get("message_id")

async def download_file(url: str, dest_path: str):
    try:
        response = await asyncio.to_thread(requests.get, url, stream=True, timeout=15)
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(response.raw, f)
    except asyncio.CancelledError:
        print("Download task was cancelled.")
        raise

def delete_message(bot_token: str, chat_id: str, message_id: int):
    try:
        requests.post(f"https://api.telegram.org/bot{bot_token}/deleteMessage",
                      json={"chat_id": chat_id, "message_id": message_id})
    except:
        pass

@app.post("/api/download")
async def download_handler(request: Request):
    temp_file = None
    message_id = None
    try:
        payload = await request.json()
        chat_id = payload.get("chat_id")
        link = payload.get("link")
        bot_token = payload.get("bot_token")

        if not all([chat_id, link, bot_token]):
            return JSONResponse(status_code=400, content={"error": "Missing fields."})

        info = get_file_info(link)

        preview_text = f"📩 *Link received!*\n⏳ *Processing...*\n🔗 *[TeraBox Link]({link})*"
        message_id = await (
            send_photo(bot_token, chat_id, info["thumbnail"], preview_text)
            if info["thumbnail"] else send_message(bot_token, chat_id, preview_text)
        )

        temp_file = os.path.join(tempfile.gettempdir(), info["name"])

        download_task = asyncio.create_task(download_file(info["download_link"], temp_file))
        try:
            await asyncio.wait_for(download_task, timeout=25)
        except asyncio.TimeoutError:
            download_task.cancel()
            await send_message(bot_token, chat_id, "⚠️ *Download timed out. Please try a smaller file.*")
            if message_id:
                delete_message(bot_token, chat_id, message_id)
            return JSONResponse(status_code=504, content={"error": "Download timed out"})

        with open(temp_file, "rb") as f:
            files = {"document": (info["name"], f)}
            data = {
                "chat_id": chat_id,
                "caption": f"📄 *{info['name']}*\n💾 *{info['size_str']}*\n🔗 *{link}*",
                "parse_mode": "Markdown"
            }
            requests.post(f"https://api.telegram.org/bot{bot_token}/sendDocument", files=files, data=data)

        if message_id:
            delete_message(bot_token, chat_id, message_id)

        return {"status": "success", "message": "File sent to Telegram"}

    except Exception as e:
        if message_id:
            await send_message(bot_token, chat_id, f"❌ *Error occurred:* {str(e)}")
            delete_message(bot_token, chat_id, message_id)
        return JSONResponse(status_code=500, content={"error": str(e)})

    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass

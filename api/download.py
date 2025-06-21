import os
import traceback
import asyncio
import tempfile
import requests
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
active_downloads = set()

async def send_message(bot_token, chat_id, text):
    resp = await asyncio.to_thread(
        requests.post,
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
    )
    return resp.json().get("result", {}).get("message_id")

async def edit_message(bot_token, chat_id, message_id, new_text):
    await asyncio.to_thread(
        requests.post,
        f"https://api.telegram.org/bot{bot_token}/editMessageText",
        json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": new_text,
            "parse_mode": "Markdown"
        }
    )

async def delete_message(bot_token, chat_id, message_id):
    await asyncio.to_thread(
        requests.post,
        f"https://api.telegram.org/bot{bot_token}/deleteMessage",
        json={
            "chat_id": chat_id,
            "message_id": message_id
        }
    )

@app.post("/api/download")
async def download_handler(request: Request):
    chat_id = None
    progress_message_id = None
    try:
        payload = await request.json()
        chat_id = payload.get("chat_id")
        link = payload.get("link")
        bot_token = payload.get("bot_token")
        user_name = payload.get("user_name", "User")

        if not all([chat_id, link, bot_token]):
            return JSONResponse(status_code=400, content={"error": "Missing fields."})

        if chat_id in active_downloads:
            await send_message(bot_token, chat_id, "⚠️ *Please wait until your current download is complete.*")
            return JSONResponse(status_code=429, content={"error": "Download already in progress for this user."})

        active_downloads.add(chat_id)

        # Fetch download URL
        api_url = f"https://teraboxvideodl.pages.dev/api/?url={link}&server=1"
        response = await asyncio.to_thread(requests.get, api_url)
        data = response.json()

        if "download_url" not in data:
            return JSONResponse(status_code=500, content={"error": "Failed to fetch download URL."})

        file_name = data.get("name", "video.mp4")
        download_url = data["download_url"]

        # Start progress message
        progress_message_id = await send_message(bot_token, chat_id, f"⬇️ *Downloading:* `{file_name}`")

        # Begin download with progress
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, file_name)

        start_time = time.time()
        downloaded = 0
        last_update = time.time()

        with open(file_path, "wb") as f:
            file_response = await asyncio.to_thread(requests.get, download_url, stream=True)
            total = int(file_response.headers.get('content-length', 0))

            for chunk in file_response.iter_content(chunk_size=65536):  # 64KB chunks
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if now - last_update > 2:
                        percent = downloaded / total * 100
                        speed = downloaded / (now - start_time)
                        eta = (total - downloaded) / speed if speed else 0
                        text = (
                            f"⬇️ *Downloading:* `{file_name}`\n\n"
                            f"🔴 [{'█' * int(percent / 5):<20}] {percent:.1f}%\n"
                            f"💾 {downloaded / 1024:.2f} KiB / {total / 1024 / 1024:.2f} MiB\n\n"
                            f"⚡ *Speed:* {speed / 1024:.2f} KiB/s\n"
                            f"⏱️ *ETA:* {int(eta)}s\n"
                            f"👤 *User:* {user_name}"
                        )
                        await edit_message(bot_token, chat_id, progress_message_id, text)
                        last_update = now

        # Final edit before upload
        await edit_message(bot_token, chat_id, progress_message_id, f"✅ *Download Complete!*\n\n*File:* `{file_name}`\n🔄 Uploading...")

        # Upload file
        with open(file_path, "rb") as f:
            files = {"document": (file_name, f)}
            data = {"chat_id": chat_id, "caption": file_name}
            await asyncio.to_thread(
                requests.post,
                f"https://api.telegram.org/bot{bot_token}/sendDocument",
                files=files,
                data=data
            )

        # Delete the progress message after sending
        if progress_message_id:
            await delete_message(bot_token, chat_id, progress_message_id)

        return {"status": "success", "message": "File uploaded"}

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

    finally:
        if chat_id:
            active_downloads.discard(chat_id)

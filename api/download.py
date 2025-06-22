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
        try:
            resp = requests.get(api_url, timeout=10)
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
        except Exception as e:
            print(f"Server {server} failed: {e}")
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
        response = await asyncio.to_thread(requests.get, url, stream=True, timeout=55)
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(response.raw, f)
    except asyncio.CancelledError:
        print("⛔ Download cancelled due to timeout.")
        raise
    except Exception as e:
        print(f"⚠️ Download failed: {e}")
        raise

def delete_message(bot_token: str, chat_id: str, message_id: int):
    try:
        requests.post(f"https://api.telegram.org/bot{bot_token}/deleteMessage",
                      json={"chat_id": chat_id, "message_id": message_id})
    except Exception as e:
        print(f"Delete failed: {e}")

@app.post("/api/download")
async def download_handler(request: Request):
    temp_file = None
    preview_message_id = None
    start_message_id = None
    download_task = None

    try:
        payload = await request.json()
        chat_id = payload.get("chat_id")
        link = payload.get("link")
        bot_token = payload.get("bot_token")
        start_message_id = payload.get("start_message_id")

        if not all([chat_id, link, bot_token]):
            return JSONResponse(status_code=400, content={"error": "Missing fields."})

        # Step 1: Get file info (blocking)
        info = get_file_info(link)

        # Step 2: Send processing message
        preview_text = f"📩 *Link received!*\n⏳ *Processing...*\n🔗 *[TeraBox Link]({link})*"
        preview_message_id = await (
            send_photo(bot_token, chat_id, info["thumbnail"], preview_text)
            if info["thumbnail"] else send_message(bot_token, chat_id, preview_text)
        )

        # Step 3: Prepare file path
        temp_file = os.path.join(tempfile.gettempdir(), info["name"])
        download_task = asyncio.create_task(download_file(info["download_link"], temp_file))

        # Step 4: Attempt to download with timeout
        try:
            await asyncio.wait_for(download_task, timeout=55)
        except asyncio.TimeoutError:
            # Cancel task and do no more work — STOP
            download_task.cancel()
            try:
                await download_task  # Ensures task is cleaned
            except:
                pass
            if preview_message_id:
                delete_message(bot_token, chat_id, preview_message_id)
            if start_message_id:
                delete_message(bot_token, chat_id, start_message_id)

            # Notify user once
            await send_message(bot_token, chat_id, "⚠️ *Download timed out. Please try again with a smaller file.*")
            return JSONResponse(status_code=504, content={"error": "Timeout: download cancelled"})

        # Step 5: Send file to Telegram
        with open(temp_file, "rb") as f:
            files = {"document": (info["name"], f)}
            data = {
                "chat_id": chat_id,
                "caption": f"📄 *{info['name']}*\n💾 *{info['size_str']}*\n🔗 *{link}*",
                "parse_mode": "Markdown"
            }
            requests.post(f"https://api.telegram.org/bot{bot_token}/sendDocument", files=files, data=data)

        # Step 6: Delete messages after success
        if preview_message_id:
            delete_message(bot_token, chat_id, preview_message_id)
        if start_message_id:
            delete_message(bot_token, chat_id, start_message_id)

        return {"status": "success", "message": "File sent to Telegram"}

    except Exception as e:
        print(f"❌ Error occurred: {e}")
        if preview_message_id:
            delete_message(bot_token, chat_id, preview_message_id)
            await send_message(bot_token, chat_id, f"❌ *Error occurred:* {str(e)}")
        if start_message_id:
            delete_message(bot_token, chat_id, start_message_id)
        return JSONResponse(status_code=500, content={"error": str(e)})

    finally:
        # Cleanup temporary file
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as e:
                print(f"⚠️ Temp cleanup failed: {e}")

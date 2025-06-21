import os
import tempfile
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from TeraboxDL import TeraboxDL  # pip install terabox-downloader
import requests

app = FastAPI()

# Replace with your cookie (format: "lang=...; ndus=...")
COOKIE = os.getenv("TERABOX_COOKIE", "lang=en; ndus=Y2f2tB1peHuigEgX5NpHQFeiY88k9XMojvuvxNVb")
terabox = TeraboxDL(COOKIE)

async def send_photo_message(bot_token: str, chat_id: str, photo: str, caption: str):
    await asyncio.to_thread(requests.post,
        f"https://api.telegram.org/bot{bot_token}/sendPhoto",
        json={"chat_id": chat_id, "photo": photo,
              "caption": caption, "parse_mode": "Markdown"}
    )

async def send_telegram_message(bot_token: str, chat_id: str, text: str):
    await asyncio.to_thread(requests.post,
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text,
              "parse_mode": "Markdown",
              "disable_web_page_preview": True}
    )

@app.post("/api/download")
async def download_handler(request: Request):
    payload = await request.json()
    chat_id = payload.get("chat_id")
    link = payload.get("link")
    bot_token = payload.get("bot_token")

    if not all([chat_id, link, bot_token]):
        return JSONResponse(status_code=400, content={"error": "Missing fields."})

    # Fetch file info
    file_info = terabox.get_file_info(link)
    if "error" in file_info:
        return JSONResponse(status_code=500, content={"error": file_info["error"]})

    # Notify user
    caption = (
        f"📩 *Link received!*\n🔗 [TeraBox Link]({link})\n"
        f"📄 *{file_info['file_name']}*\n💾 *{file_info['file_size']}*"
    )
    if file_info.get("thumbnail"):
        await send_photo_message(bot_token, chat_id, file_info["thumbnail"], caption)
    else:
        await send_telegram_message(bot_token, chat_id, caption)

    # Download to temp
    temp_dir = tempfile.gettempdir()
    result = terabox.download(file_info, save_path=temp_dir)
    if "error" in result:
        return JSONResponse(status_code=500, content={"error": result["error"]})

    file_path = result["file_path"]
    try:
        # Send to Telegram
        with open(file_path, "rb") as f:
            files = {"document": (file_info["file_name"], f)}
            data = {"chat_id": chat_id,
                    "caption": caption}
            await asyncio.to_thread(requests.post,
                f"https://api.telegram.org/bot{bot_token}/sendDocument",
                files=files, data=data
            )
        return {"status": "success", "message": "Sent successfully"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        os.remove(file_path)

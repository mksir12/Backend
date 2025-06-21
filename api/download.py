import os
import traceback
import asyncio
import tempfile
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

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
    try:
        payload = await request.json()
        chat_id = payload.get("chat_id")
        link = payload.get("link")
        bot_token = payload.get("bot_token")

        if not all([chat_id, link, bot_token]):
            return JSONResponse(status_code=400, content={"error": "Missing fields."})

        # External API call
        api_url = f"https://teraboxvideodl.pages.dev/api/?url={link}&server=1"
        response = await asyncio.to_thread(requests.get, api_url)
        data = response.json()

        if "download_url" not in data:
            return JSONResponse(status_code=500, content={"error": "Failed to fetch download URL."})

        file_name = data.get("name", "terabox_video.mp4")
        file_size = data.get("size", "Unknown size")
        image = data.get("image")
        download_url = data["download_url"]

        caption = (
            f"📩 *Link received!*\n🔗 [TeraBox Link]({link})\n"
            f"📄 *{file_name}*\n💾 *{file_size}*"
        )

        if image:
            await send_photo_message(bot_token, chat_id, image, caption)
        else:
            await send_telegram_message(bot_token, chat_id, caption)

        # Download to temp
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, file_name)

        with open(file_path, "wb") as f:
            file_response = await asyncio.to_thread(requests.get, download_url, stream=True)
            for chunk in file_response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        # Send file to Telegram
        with open(file_path, "rb") as f:
            files = {"document": (file_name, f)}
            data = {"chat_id": chat_id, "caption": caption}
            await asyncio.to_thread(
                requests.post,
                f"https://api.telegram.org/bot{bot_token}/sendDocument",
                files=files,
                data=data
            )

        return {"status": "success", "message": "File sent successfully"}

    except Exception as e:
        print("❌ Exception occurred:")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

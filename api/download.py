import os, shutil, tempfile, asyncio, requests, re
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from urllib.parse import urlencode, urlparse, parse_qs

app = FastAPI()
COOKIE = "ndus=Y2f2tB1peHuigEgX5NpHQFeiY88k9XMojvuvxNVb"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": COOKIE,
}
DL_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Referer": "https://www.terabox.com/",
    "Connection": "keep-alive",
    "Cookie": COOKIE,
}

def get_size(n): return (
    f"{n/1024**3:.2f} GB" if n>=1024**3 else
    f"{n/1024**2:.2f} MB" if n>=1024**2 else
    f"{n/1024:.2f} KB" if n>=1024 else
    f"{n} bytes"
)

def extract_token(pat, txt):
    m = re.search(pat, txt)
    return m.group(1) if m else None

def get_file_info(share_url):
    r = requests.get(share_url, headers=HEADERS, allow_redirects=True)
    r.raise_for_status()
    final = r.url
    surl = parse_qs(urlparse(final).query).get("surl", [None])[0]
    if not surl: raise ValueError("Invalid share URL")

    html = requests.get(final, headers=HEADERS).text

    js_token = extract_token(r'fn\([^,]*\(["\']([^"\']+?)["\']\)', html)
    logid = extract_token(r'dp-logid=([A-Za-z0-9]+)', html)

    if not js_token or not logid:
        print("⚠️ js_token =", js_token)
        print("⚠️ logid =", logid)
        print("⚠️ HTML snippet:", html[:500])
        raise ValueError("Failed to extract tokens")

    params = {
        "app_id": "250528","web":"1","channel":"dubox",
        "clienttype":"0","jsToken":js_token,"dp-logid":logid,
        "page":"1","num":"20","by":"name","order":"asc",
        "site_referer": final,"shorturl": surl,"root": "1,"
    }
    info = requests.get("https://www.terabox.app/share/list?" + urlencode(params), headers=HEADERS).json()
    if info.get("errno") or not info.get("list"):
        raise ValueError("API error: " + info.get("errmsg",""))

    f = info["list"][0]
    sz = int(f.get("size", 0))
    return {"name": f.get("server_filename","file"), "download_link": f.get("dlink"), "size_str": get_size(sz)}

async def send_tg(bot_token, chat_id, text):
    await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{bot_token}/sendMessage",
                            json={"chat_id":chat_id,"text":text,"parse_mode":"Markdown","disable_web_page_preview":True})

@app.post("/api/download")
async def download_handler(req: Request):
    temp = None
    try:
        data = await req.json()
        cid, link, tok = data.get("chat_id"), data.get("link"), data.get("bot_token")
        if not all([cid, link, tok]):
            return JSONResponse(400, {"error":"Missing chat_id, link or bot_token"})
        await send_tg(tok, cid, f"📩 *Link received!*\n⏳ Parsing...\n🔗 [TeraBox Link]({link})")
        info = get_file_info(link)
        await send_tg(tok, cid, f"⏳ *Downloading...*\n📄 *{info['name']}*\n💾 *{info['size_str']}*")
        temp = os.path.join(tempfile.gettempdir(), info["name"])
        with requests.get(info["download_link"], headers=DL_HEADERS, stream=True) as r2:
            r2.raise_for_status()
            with open(temp, "wb") as out:
                shutil.copyfileobj(r2.raw, out)
        with open(temp, "rb") as out:
            requests.post(f"https://api.telegram.org/bot{tok}/sendDocument",
                          files={"document":(info["name"],out)},
                          data={"chat_id":cid,"caption":f"📄 {info['name']}\n💾 {info['size_str']}\n🔗 {link}"})
        return {"status":"success"}
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse(500, {"error": str(e)})
    finally:
        if temp and os.path.exists(temp):
            try: os.remove(temp)
            except: pass

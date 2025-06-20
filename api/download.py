# download.py
# Please give credits https://github.com/MN-BOTS
#  @MrMNTG @MusammilN

import os
import tempfile
import shutil
import requests
from urllib.parse import urlencode, urlparse, parse_qs
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse, FileResponse

app = FastAPI()

COOKIE = "ndus=YzrYlCHteHuixx7IN5r0fc3sajSOYAHfqDoPM0dP"  # Add your own cookie here

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    "Connection": "keep-alive",
    "DNT": "1",
    "Host": "www.terabox.app",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"),
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
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/91.0.4472.124 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;"
              "q=0.9,image/webp,*/*;q=0.8",
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
        raise HTTPException(status_code=400, detail=f"Failed to fetch share page ({resp.status_code})")
    final_url = resp.url

    parsed = urlparse(final_url)
    surl = parse_qs(parsed.query).get("surl", [None])[0]
    if not surl:
        raise HTTPException(status_code=400, detail="Invalid share URL (missing surl)")

    page = requests.get(final_url, headers=HEADERS)
    html = page.text

    js_token = find_between(html, 'fn%28%22', '%22%29')
    logid = find_between(html, 'dp-logid=', '&')
    bdstoken = find_between(html, 'bdstoken":"', '"')
    if not all([js_token, logid, bdstoken]):
        raise HTTPException(status_code=400, detail="Failed to extract authentication tokens")

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
        raise HTTPException(status_code=400, detail=f"List API error: {errmsg}")

    file = info["list"][0]
    size_bytes = int(file.get("size", 0))
    return {
        "name": file.get("server_filename", "download"),
        "download_link": file.get("dlink", ""),
        "size_bytes": size_bytes,
        "size_str": get_size(size_bytes)
    }

@app.get("/info")
async def file_info(url: str = Query(..., description="Terabox share URL")):
    """Get file info for a Terabox share URL."""
    info = get_file_info(url)
    return JSONResponse(content=info)

@app.get("/download")
async def file_download(url: str = Query(..., description="Terabox share URL")):
    """Download the file from Terabox share URL, stream as response."""
    info = get_file_info(url)
    temp_path = os.path.join(tempfile.gettempdir(), info["name"])

    try:
        with requests.get(info["download_link"], headers=DL_HEADERS, stream=True) as r:
            r.raise_for_status()
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(r.raw, f)

        return FileResponse(
            path=temp_path,
            filename=info["name"],
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={info['name']}",
                "X-File-Size": str(info["size_bytes"]),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

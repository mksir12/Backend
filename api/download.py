import requests
from urllib.parse import urlparse, parse_qs, urlencode
from flask import Flask, request

app = Flask(__name__)

# Full cookie header string from your export
COOKIES = (
    "lang=en;"
    "_ga_06ZNKL8C2E=GS2.1.s1750442327$o1$g1$t1750442392$j58$l0$h0;"
    "__stripe_mid=4b45b717-c613-4cb2-af79-fbafd25b88968752a4;"
    "__stripe_sid=3aab8ee5-a8e4-464b-ac12-f944c7b7359b6908fb;"
    "ndus=Y2f2tB1peHuizo9kYj3bHv9M0-40sSfDkJ7JX3FG;"
    "_ga=GA1.1.17342924.1750442327;"
    "__bid_n=1978e623a107ede4924207;"
    "_ga_HSVH9T016H=GS2.1.s1750442393$o1$g1$t1750442415$j38$l0$h0;"
    "browserid=JUdYbDmTbPJJ5l64jiEnJnx2F2x-xGT_3qZRGl9gy7e-_7ZX7frk0Nhckjs=;"
    "csrfToken=Bb-eUdOYpCPq8zMAj-JpP3zm;"
    "ndut_fmt=757D1CB569F951088BBB0306CE1E2325F4CEA1103666315D7B11C1FF85B8CAF0"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    ),
    "Accept": "*/*",
    "Cookie": COOKIES,
    "Referer": "https://www.terabox.com/"
}

def extract_between(text, start, end):
    try:
        return text.split(start, 1)[1].split(end, 1)[0]
    except Exception:
        return ""

def get_size(bytes_len: int) -> str:
    if bytes_len >= 1024 ** 3:
        return f"{bytes_len / 1024**3:.2f} GB"
    if bytes_len >= 1024 ** 2:
        return f"{bytes_len / 1024**2:.2f} MB"
    if bytes_len >= 1024:
        return f"{bytes_len / 1024:.2f} KB"
    return f"{bytes_len} bytes"

def get_file_info(terabox_url):
    session = requests.Session()
    page = session.get(terabox_url, headers=HEADERS)

    # Check if redirected to login page or blocked
    if "login" in page.url.lower() or "登录" in page.text or "Log in" in page.text:
        raise Exception("❌ Cookie invalid or session expired (redirected to login).")

    final_url = page.url
    parsed = urlparse(final_url)
    surl = parse_qs(parsed.query).get("surl", [None])[0]
    if not surl:
        raise Exception("❌ Invalid Terabox link (missing 'surl' param).")

    # Extract tokens from page HTML
    js_token = extract_between(page.text, 'fn%28%22', '%22%29')
    logid = extract_between(page.text, 'dp-logid=', '&')
    bdstoken = extract_between(page.text, 'bdstoken":"', '"')

    # DEBUG: print tokens
    print("[DEBUG] js_token:", js_token)
    print("[DEBUG] logid:", logid)
    print("[DEBUG] bdstoken:", bdstoken)

    missing = []
    if not js_token:
        missing.append("js_token")
    if not logid:
        missing.append("logid")
    if not bdstoken:
        missing.append("bdstoken")
    if missing:
        raise Exception(f"❌ Failed to extract tokens: {', '.join(missing)}")

    # Build API request parameters
    params = {
        "app_id": "250528",
        "web": "1",
        "channel": "dubox",
        "clienttype": "0",
        "jsToken": js_token,
        "dp-logid": logid,
        "bdstoken": bdstoken,
        "page": "1",
        "num": "20",
        "by": "name",
        "order": "asc",
        "site_referer": final_url,
        "shorturl": surl,
        "root": "1,"
    }

    # Request file list from Terabox API
    api_url = "https://www.terabox.app/share/list?" + urlencode(params)
    resp = session.get(api_url, headers=HEADERS)

    data = resp.json()
    if not data.get("list"):
        raise Exception("❌ File list empty — file might be private, deleted, or cookie invalid.")

    file = data["list"][0]
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

        # Download the actual file content
        file_response = requests.get(file_info["link"], headers=HEADERS)
        file_response.raise_for_status()

        tg_api = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        files = {
            "document": (file_name, file_response.content)
        }
        data = {
            "chat_id": chat_id,
            "caption": f"📄 {file_name}\n💾 {file_size}\n🔗 {terabox_link}"
        }
        requests.post(tg_api, data=data, files=files)
        return "OK", 200

    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        try:
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": error_msg}
            )
        except:
            pass
        return "Failed", 500

if __name__ == "__main__":
    app.run(port=5000)

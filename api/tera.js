import axios from "axios";

const COOKIE = "ndus=Y2f2tB1peHuigEgX5NpHQFeiY88k9XMojvuvxNVb";

const HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/135.0.0.0 Safari/537.36",
  Cookie: COOKIE,
};

function getSize(bytes) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${bytes} bytes`;
}

function extractToken(pattern, text) {
  const match = text.match(pattern);
  return match ? match[1] : null;
}

async function getFileInfo(shareUrl) {
  try {
    const response = await axios.get(shareUrl, { headers: HEADERS, maxRedirects: 5 });
    const finalUrl = response.request.res.responseUrl || shareUrl;
    const surl = new URL(finalUrl).searchParams.get("surl");
    if (!surl) throw new Error("Invalid TeraBox URL or missing 'surl' param");

    const html = response.data;

    const thumbUrl = extractToken(/<meta property="og:image" content="([^"]+)"/, html);
    const jsToken = extractToken(/fn%28%22([A-F0-9]{64,})%22\)/, html);
    const logid = extractToken(/dp-logid=([a-zA-Z0-9]+)&/, html);

    if (!jsToken || !logid) {
      throw new Error("Missing required tokens in page content");
    }

    const params = new URLSearchParams({
      app_id: "250528",
      web: "1",
      channel: "dubox",
      clienttype: "0",
      jsToken,
      "dp-logid": logid,
      page: "1",
      num: "20",
      by: "name",
      order: "asc",
      site_referer: finalUrl,
      shorturl: surl,
      root: "1",
    });

    const apiUrl = `https://www.terabox.app/share/list?${params.toString()}`;
    const fileRes = await axios.get(apiUrl, { headers: HEADERS });
    const fileList = fileRes.data.list;

    if (!fileList || fileList.length === 0) {
      throw new Error("No file found or access denied");
    }

    const file = fileList[0];
    const size = parseInt(file.size, 10);

    return {
      name: file.server_filename,
      size: getSize(size),
      size_bytes: size,
      download_link: file.dlink,
      thumbnail: thumbUrl,
      original_url: shareUrl,
    };
  } catch (err) {
    throw new Error(`Error: ${err.message}`);
  }
}

export default async function handler(req, res) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "Method Not Allowed" });
  }
  const { url } = req.query;
  if (!url) {
    return res.status(400).json({ error: "Missing 'url' query parameter" });
  }

  try {
    const info = await getFileInfo(url);
    res.status(200).json({ status: "success", ...info });
  } catch (err) {
    res.status(500).json({ status: "error", message: err.message });
  }
}

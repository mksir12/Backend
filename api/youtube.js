const ytdl = require("ytdl-core");
const yts = require("yt-search");

module.exports = async (req, res) => {
  try {
    const { query } = req;
    const input = query.search;

    if (!input) return res.status(400).json({ error: "Missing search parameter" });

    // search YouTube
    let ytSearch = await yts(input);
    if (!ytSearch.videos.length) return res.status(404).json({ error: "No videos found" });

    let { title, url, thumbnail, description, views, ago, duration } = ytSearch.videos[0];

    // get video + audio download links
    let info = await ytdl.getInfo(url);
    let formats = ytdl.filterFormats(info.formats, "audioandvideo");
    let audioFormats = ytdl.filterFormats(info.formats, "audioonly");

    let resultados = {
      title,
      description,
      views,
      ago,
      duration,
      url,
      thumbnail,
      video: {
        dl_link: formats[0]?.url,
        quality: formats[0]?.qualityLabel,
      },
      audio: {
        dl_link: audioFormats[0]?.url,
      },
    };

    res.status(200).json(resultados);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
};

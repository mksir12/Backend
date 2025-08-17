const { ytmp4, ytmp3 } = require("ruhend-scraper");
const yts = require("yt-search");

module.exports = async (req, res) => {
  try {
    const { query } = req; // Example: /api/youtube?search=naruto
    const input = query.search;

    if (!input) {
      return res.status(400).json({ error: "Missing search parameter" });
    }

    let ytSearch = await yts(input);
    if (!ytSearch.videos || ytSearch.videos.length === 0) {
      return res.status(404).json({ error: "No videos found" });
    }

    let { title, url, thumbnail, description, views, ago, duration } =
      ytSearch.videos[0];

    let { video, quality, size } = await ytmp4(url);
    let { audio } = await ytmp3(url);

    let resultados = {
      title,
      description,
      views,
      ago,
      duration,
      url,
      thumbnail,
      video: {
        dl_link: video,
        size,
        quality,
      },
      audio: {
        dl_link: audio,
      },
    };

    res.status(200).json(resultados);
  } catch (err) {
    res.status(500).json({ error: err.message || "Internal Server Error" });
  }
};

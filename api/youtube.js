const ytdl = require("ytdl-core");
const yts = require("yt-search");

module.exports = async (req, res) => {
  try {
    const { query } = req;
    const search = query.search || query.url;

    if (!search) return res.status(400).json({ error: "Missing search or url parameter" });

    let video;

    if (ytdl.validateURL(search)) {
      // if user passed a YouTube URL
      const info = await ytdl.getInfo(search);
      video = {
        title: info.videoDetails.title,
        description: info.videoDetails.description,
        url: info.videoDetails.video_url,
        thumbnail: info.videoDetails.thumbnails.pop().url,
        views: info.videoDetails.viewCount,
        duration: info.videoDetails.lengthSeconds,
        ago: info.videoDetails.publishDate,
      };
    } else {
      // otherwise, run a search
      let ytSearch = await yts(search);
      if (!ytSearch.videos.length) return res.status(404).json({ error: "No videos found" });
      video = ytSearch.videos[0];
    }

    // fetch video + audio download links
    let info = await ytdl.getInfo(video.url);
    let videoFormats = ytdl.filterFormats(info.formats, "audioandvideo");
    let audioFormats = ytdl.filterFormats(info.formats, "audioonly");

    let result = {
      title: video.title,
      description: video.description,
      views: video.views,
      ago: video.ago,
      duration: video.duration,
      url: video.url,
      thumbnail: video.thumbnail,
      video: {
        dl_link: videoFormats[0]?.url,
        quality: videoFormats[0]?.qualityLabel,
      },
      audio: {
        dl_link: audioFormats[0]?.url,
      },
    };

    res.status(200).json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
};

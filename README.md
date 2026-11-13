# What If… For 5 Seconds

Faceless YouTube Shorts / Reels channel: animated "What If" science videos.

- `docs/what-if-playbook.html`: the format, specs, topics and cost per video
- `pipeline/build.py`: builds a finished 1080x1920 Short from an episode folder
- `episodes/<ep>/`: `episode.json` (shots, cues, badges, visual prompts), `voice.mp3`, `words.json`, `shots/`, optional `music.mp3`
- `assets/`: mascot reference sheet and caption fonts

Build an episode (needs ffmpeg):

    python3 pipeline/build.py episodes/ep01-friction

Output: `episodes/<ep>/out/final.mp4` (not committed; rebuild any time).

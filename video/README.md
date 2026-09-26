# Videos

`make_videos.py` builds the teaser (~1 min) and the judging video (≤ 3 min) from the running app.

```bash
make offline                      # in another terminal: the app on http://localhost:8000
pip install playwright && python -m playwright install chromium
python video/make_videos.py all   # or: teaser | judging
```

- `segments.py`: the script: Indonesian narration, English subtitles, and the scene for each segment
- `cards.py`: animated title cards, subtitle and thumbnail templates (HTML)
- Narration uses macOS `say` (voice "Damayanti"); if a video would exceed its limit, the voice
  is sped up automatically.
- Each scene is recorded in headless Chromium for exactly the length of its narration, with a
  visible cursor. This ffmpeg build has no subtitle filter, so captions are rendered as images and
  overlaid.

Output (`video/out/`, git-ignored): MP4s, `.srt` captions in Indonesian and English,
thumbnails, and `youtube-upload.md` with titles, descriptions, chapters and tags.

To use your own voice: record one audio file per segment in `segments.py` order, replace the
`narr_XX.wav` files in `video/build/<video>/`, and adjust `build_narration` to skip TTS.

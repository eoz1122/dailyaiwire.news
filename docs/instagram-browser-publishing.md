# Browser-only Instagram publishing

DailyAIWire publishes to Instagram through the signed-in in-app browser. The
Instagram and Meta APIs remain disabled.

## Daily format schedule

- 09:00 Europe/Berlin: static 1080 x 1350 PNG
- 14:00 Europe/Berlin: five-slide 1080 x 1350 carousel
- 19:00 Europe/Berlin: silent 1080 x 1920 H.264 Reel-ready MP4

The browser automation selects the requested format explicitly:

```bash
scripts/instagram_browser_queue.py next --lookback-hours 48 --format static
scripts/instagram_browser_queue.py next --lookback-hours 48 --format carousel
scripts/instagram_browser_queue.py next --lookback-hours 48 --format reel
```

Each successful response contains `content_format`, `media_urls`, and the
caption. Static posts also include `image_url`; Reels include `video_url`.
The browser must validate every asset and confirm the canonical Instagram
permalink before the safe `posted` command changes publication state.

## Fail-closed checks

- Never call the Instagram or Meta API.
- Never mark an article shared before visible publication confirmation.
- Reject a carousel unless all five portrait slides are available.
- Reject a Reel unless it is 1080 x 1920 H.264 with `yuv420p` pixel format.
- Reject unsafe crops, stretched media, duplicate uncertainty, authentication
  blocks, and CAPTCHA challenges.
- Remove per-run temporary downloads after success or failure.

## Rollback

Restore the prior queue, route, templates, and generator files from the
deployment backup, then return the automation prompt to the static-only
`next --lookback-hours 48` command. Existing versioned social assets are
immutable and can remain until no published post references them.

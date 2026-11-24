# Tricky bugs

Incident notes for non-obvious failures when exporting Thinkific course media.

## Wistia progressive download — RemoteDisconnected

### Symptom

`cggt_export_course_media` prints playlist and progressive download URLs, tqdm stays at `0.00B` for tens of seconds, then aborts with:

```text
http.client.RemoteDisconnected: Remote end closed connection without response
```

The stack trace points at `PlayerClient._open` / `urllib.request.urlopen` while fetching a `embed-ssl.wistia.com/deliveries/*.bin` URL.

### Root cause

Two stacked issues:

1. Video file downloads default to `send_cookie=True`, so Thinkific session cookies were sent to Wistia CDN hosts that do not need them (JSON metadata already used `send_cookie=False`).
2. Wistia delivery hosts occasionally drop the TCP connection before HTTP headers on large progressive assets; `urllib.request.urlopen` had no timeout or retry, so one flake killed the whole export.

### Why it was tricky

- The m3u8 playlist download succeeds quickly and tqdm ignores its byte progress, so the bar shows `0.00B` while the failure is on the next URL (the large `.bin` / mp4 delivery).
- `curl -I` against the same URL often succeeds; the failure is intermittent at connection setup, not a steady 403/404.

### Fix

- Set `send_cookie: False` on every Wistia download entry in `course_media.collect_video_jobs`.
- Default missing `send_cookie` to `False` in `_download_files_into_content_directory`.
- Retry transient open failures in `player_client` (up to four attempts, 2s backoff) and use a 300s read timeout on `urlopen`.

### Prevention

- Tests assert video downloads never send cookies (`test_course_media.test_download_and_catalog_then_skip_and_merge`).
- `test_player_client.test_open_retries_remote_disconnected` locks in retry behavior.

### References

- Wistia media JSON: `https://fast.wistia.com/embed/medias/{wistia_id}.json`
- Progressive delivery URLs: `https://embed-ssl.wistia.com/deliveries/{delivery_id}.bin`
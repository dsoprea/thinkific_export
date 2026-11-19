# Features

## Course List

`cggt_course_list` loads every course and every product from the Thinkific Admin API. It prints course ID, name, and the linked product `created_at`, sorted by name. Course records themselves do not include timestamps.

## Course Export

`cggt_export_course COURSE_ID` prints one JSON document:

- `course` — `GET /courses/{id}`
- `chapters` — each chapter from `GET /chapters/{id}`, ordered by `position`, with `contents` from `GET /chapters/{id}/contents`, also ordered by `position`

## Course Video Export

`cggt_export_course_videos SESSION_FILEPATH COURSE_EXPORT_FILEPATH OUTPUT_DIRECTORY_PATH` reads a cookietruck session (`cookie_header`) and a course export. For each lesson it calls the course player, then Wistia, and downloads the M3U8 playlists and the highest-bitrate progressive file into `OUTPUT_DIRECTORY_PATH/{content_id}/`. A content-ID directory that already has files is skipped. `OUTPUT_DIRECTORY_PATH/wistia/` receives each media JSON (replaced when present) and `content_id_to_wistia_urls.json` (merged when present). Each download shows a tqdm bar labeled `{n}/{total} {lesson name}`. Lessons with no video are listed on stderr and are not part of the total. This command does not use the Admin API token.

# Features

## Course List

`cggt_course_list` loads every course and every product from the Thinkific Admin API. It prints course ID, name, and the linked product `created_at`, sorted by name. Course records themselves do not include timestamps.

## Course Export

`cggt_export_course COURSE_ID` prints one JSON document on stdout. While Admin API chapters and contents load, a tqdm progress bar on stderr shows `{n}/{total}` and the current step (course or chapter name).

Exported JSON:

- `course` — `GET /courses/{id}`
- `chapters` — each chapter from `GET /chapters/{id}`, ordered by `position`, with `contents` from `GET /chapters/{id}/contents`, also ordered by `position`

## Course Media Export

`cggt_export_course_media SESSION_FILEPATH COURSE_EXPORT_FILEPATH OUTPUT_DIRECTORY_PATH` reads a [cookietruck](https://github.com/dsoprea/cookietruck) session (`cookie_header`) and a course export. It uses the course player API (not the Admin API token) to resolve `contentable_id` values, then downloads media under typed subdirectories:

| Kind | Subdirectory | Files |
| --- | --- | --- |
| Lesson video | `videos/{content_id}/` | M3U8 playlists, `video.mp4` (highest-bitrate progressive), `metadata.json` |
| PDF | `documents/{content_id}/` | `document` + extension from the CDN URL, `metadata.json` |
| Quiz | `quizzes/{content_id}/` | `quiz.json` (full player payload), `metadata.json` |

`metadata.json` in each content directory lists shared fields (`content_id`, `name`, `contentable_type`, `contentable_id`, optional `chapter_id`) and a `content_specific` object for type-only fields (for example Wistia ID, PDF URL, quiz question count). A content-ID directory that already has files is skipped. `videos/wistia/` stores each Wistia media JSON (replaced when present) and `content_id_to_wistia_urls.json` (merged when present). Lesson video downloads show a tqdm bar labeled `{n}/{total} {lesson name}` for progressive files; M3U8 downloads do not advance that bar. Lessons with no video and unresolved PDFs or quizzes are listed on stderr.

Optional flags `--videos`, `--documents`, and `--quizzes` limit which kinds run. When any flag is present, only the selected kinds run; with no flags, all three run.

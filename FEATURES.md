# Features

## Course List

`cggt_course_list` loads every course and every product from the Thinkific Admin API. It prints course ID, name, and the linked product `created_at`, sorted by name. Course records themselves do not include timestamps.

## Course Export

`cggt_export_course COURSE_ID` prints one JSON document:

- `course` — `GET /courses/{id}`
- `chapters` — each chapter from `GET /chapters/{id}`, ordered by `position`, with `contents` from `GET /chapters/{id}/contents`, also ordered by `position`

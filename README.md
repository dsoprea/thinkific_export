# cggt

Read a Thinkific site's courses with the Admin API.

The course domain covers catalog listing and content export. Capabilities are in [FEATURES.md](FEATURES.md).

## Prerequisites

- Python 3.14 (this repo's `.python-version`)
- Network access to `https://api.thinkific.com`

## Environment

Export these before running a command. They are not loaded from a file.

| Variable | Role |
| --- | --- |
| `THINKIFIC_API_ACCESS_TOKEN` | Bearer token for `GET` requests (`Authorization: Bearer`) |
| `THINKIFIC_SSO_SIGNING_SECRET` | Site SSO signing secret. Required to be set. These two commands do not sign SSO payloads. |

## Install

```bash
./script/install.sh
```

## Commands

```bash
cggt_course_list
cggt_export_course COURSE_ID
cggt_export_course_videos SESSION_FILEPATH COURSE_EXPORT_FILEPATH OUTPUT_DIRECTORY_PATH
```

`cggt_course_list` writes a table to stderr. `cggt_export_course` writes JSON to stdout. `cggt_export_course_videos` does not use the Admin API token. `SESSION_FILEPATH` is [cookietruck](https://github.com/dsoprea/cookietruck) JSON with a `cookie_header` string. Progress and skip lines go to stderr.

## Test

```bash
./script/test.sh
```

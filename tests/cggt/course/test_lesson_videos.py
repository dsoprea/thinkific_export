"""Lesson video URL selection and on-disk layout."""

import json
import os

import cggt.course.lesson_videos


def _build_course_document():
    """Return two lessons and one quiz."""

    return {
        "chapters": [
            {
                "contents": [
                    {
                        "id": 11,
                        "name": "With Video",
                        "contentable_type": "Lesson",
                        "take_url": "https://creatify.thinkific.com/courses/take/demo/lessons/11-with-video",
                    },
                    {
                        "id": 12,
                        "name": "No Video",
                        "contentable_type": "Lesson",
                        "take_url": "https://creatify.thinkific.com/courses/take/demo/lessons/12-no-video",
                    },
                    {
                        "id": 14,
                        "name": "Not In Player",
                        "contentable_type": "Lesson",
                        "take_url": "https://creatify.thinkific.com/courses/take/demo/lessons/14-not-in-player",
                    },
                    {
                        "id": 13,
                        "name": "Quiz",
                        "contentable_type": "Quiz",
                        "take_url": "https://creatify.thinkific.com/courses/take/demo/quizzes/13-quiz",
                    },
                ],
            },
        ],
    }


def _build_media_document():
    """Return one HLS asset and two progressive assets."""

    return {
        "media": {
            "assets": [
                {
                    "type": "hls_video",
                    "url": "https://cdn.example/playlist.m3u8",
                },
                {
                    "type": "mp4_video",
                    "url": "https://cdn.example/low.mp4",
                    "bitrate": 100,
                },
                {
                    "type": "original",
                    "url": "https://cdn.example/high.mp4",
                    "bitrate": 400,
                },
            ],
        },
    }


class _FakePlayerClient:
    """Returns a fixed lesson payload and records downloads."""

    def __init__(self):
        """Start with no downloads."""

        self.downloaded_urls = []

    def get_json(self, url, send_cookie):
        """Return the course, lesson, or media document for the test URLs."""

        if url.endswith("/courses/demo"):
            assert send_cookie is True

            return {
                "contents": [
                    {"id": 11, "contentable_type": "Lesson", "contentable_id": 501},
                    {"id": 12, "contentable_type": "Lesson", "contentable_id": 502},
                ],
            }
        if url.endswith("/lessons/501"):
            return {
                "lesson": {
                    "video_id": 9,
                    "video_url": "https://creatify.thinkific.com/play/11",
                },
            }
        if url.endswith("/lessons/502"):
            return {"lesson": {"video_id": None, "video_url": None}}
        assert "abc123" in url

        return _build_media_document()

    def get_text(self, url, send_cookie):
        """Return a play page that names the Wistia hashed ID."""

        assert send_cookie is True

        return '<script src="https://fast.wistia.com/embed/medias/abc123.jsonp"></script>'

    def download_file(self, url, destination_filepath, on_chunk):
        """Write the URL text and report a fixed length."""

        self.downloaded_urls.append(url)
        on_chunk(0, 4)
        with open(destination_filepath, "w", encoding="utf-8") as destination_file:
            destination_file.write("data")
        on_chunk(4, None)


def _ignore_operation(message):
    """Discard operation lines in unit tests."""

    return None


def test_collect_lesson_video_jobs_omits_lessons_without_video():
    """Only the lesson with a Wistia ID becomes a job, and the high bitrate file is chosen."""

    client = _FakePlayerClient()
    jobs, lessons_without_video = cggt.course.lesson_videos.collect_lesson_video_jobs(
        client,
        _build_course_document(),
        _ignore_operation)

    assert len(jobs) == 1
    assert jobs[0]["content_id"] == 11
    assert jobs[0]["wistia_id"] == "abc123"
    assert jobs[0]["video_urls"] == [
        "https://fast.wistia.net/embed/medias/abc123.m3u8",
        "https://cdn.example/playlist.m3u8",
        "https://cdn.example/high.mp4",
    ]
    assert lessons_without_video == [
        {"content_id": 12, "lesson_name": "No Video"},
        {"content_id": 14, "lesson_name": "Not In Player"},
    ]


def test_download_and_catalog_then_skip_and_merge(tmp_path):
    """Files land under the content ID, a second run skips them, and the mapping merges."""

    output_directory_path = str(tmp_path)
    client = _FakePlayerClient()
    jobs, _lessons_without_video = cggt.course.lesson_videos.collect_lesson_video_jobs(
        client,
        _build_course_document(),
        _ignore_operation)
    cggt.course.lesson_videos.write_wistia_catalog(
        output_directory_path,
        jobs,
        _ignore_operation)
    assert cggt.course.lesson_videos.is_content_directory_present(output_directory_path, 11) is False
    cggt.course.lesson_videos.download_lesson_files(
        client,
        jobs[0],
        output_directory_path,
        lambda chunk_byte_count, content_length: None,
        _ignore_operation)
    content_directory_path = os.path.join(output_directory_path, "11")
    assert os.path.isfile(os.path.join(content_directory_path, "playlist.m3u8"))
    assert os.path.isfile(os.path.join(content_directory_path, "high.mp4"))
    assert cggt.course.lesson_videos.is_content_directory_present(output_directory_path, 11) is True
    wistia_filepath = os.path.join(output_directory_path, "wistia", "abc123.json")
    assert json.loads(open(wistia_filepath, encoding="utf-8").read())["media"]["assets"][0]["type"] == "hls_video"
    mapping_filepath = os.path.join(
        output_directory_path,
        "wistia",
        "content_id_to_wistia_urls.json")
    mapping = json.loads(open(mapping_filepath, encoding="utf-8").read())
    assert mapping["11"][0] == "https://fast.wistia.net/embed/medias/abc123.m3u8"
    mapping["99"] = ["https://cdn.example/other.mp4"]
    with open(mapping_filepath, "w", encoding="utf-8") as mapping_file:
        json.dump(mapping, mapping_file)
    replaced_media = {"media": {"assets": [], "replaced": True}}
    jobs[0]["media_document"] = replaced_media
    jobs[0]["video_urls"] = ["https://cdn.example/playlist.m3u8"]
    cggt.course.lesson_videos.write_wistia_catalog(
        output_directory_path,
        jobs,
        _ignore_operation)
    replaced = json.loads(open(wistia_filepath, encoding="utf-8").read())
    merged = json.loads(open(mapping_filepath, encoding="utf-8").read())

    assert replaced["media"]["replaced"] is True
    assert merged["99"] == ["https://cdn.example/other.mp4"]
    assert merged["11"] == ["https://cdn.example/playlist.m3u8"]
    assert client.downloaded_urls == [
        "https://fast.wistia.net/embed/medias/abc123.m3u8",
        "https://cdn.example/playlist.m3u8",
        "https://cdn.example/high.mp4",
    ]

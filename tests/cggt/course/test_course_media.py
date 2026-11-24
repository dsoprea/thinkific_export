"""Course media URL selection and on-disk layout."""

import json
import os

import cggt.course.course_media


def _build_course_document():
    """Return lessons, a PDF, and a quiz."""

    return {
        "course": {"slug": "demo"},
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
                        "id": 21,
                        "name": "Handbook",
                        "contentable_type": "Pdf",
                        "take_url": "https://creatify.thinkific.com/courses/take/demo/pdfs/21-handbook",
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
    """Returns fixed player payloads and records downloads."""

    def __init__(self):
        """Start with no downloads."""

        self.downloaded_urls = []
        self.progress_callback_ids = []
        self.send_cookie_flags = []

    def get_json(self, url, send_cookie):
        """Return the lesson, pdf, quiz, or media document for the test URLs."""

        if url.endswith("/courses/demo"):
            assert send_cookie is True

            return {
                "contents": [
                    {"id": 11, "contentable_type": "Lesson", "contentable_id": 501},
                    {"id": 12, "contentable_type": "Lesson", "contentable_id": 502},
                    {"id": 21, "contentable_type": "Pdf", "contentable_id": 601},
                    {"id": 13, "contentable_type": "Quiz", "contentable_id": 701},
                ],
            }
        if url.endswith("/lessons/501"):
            return {
                "lesson": {
                    "video_id": 9,
                    "video_url": "https://creatify.thinkific.com/play/11",
                },
                "videos": [{"id": 9, "identifier": "proxy-id"}],
            }
        if url.endswith("/lessons/502"):
            return {"lesson": {"video_id": None, "video_url": None}}
        if url.endswith("/pdfs/601"):
            return {
                "pdf": {
                    "id": 88,
                    "url": "https://cdn.example/handbook.pdf",
                    "downloadable": True,
                },
            }
        if url.endswith("/quizzes/701"):
            return {
                "quiz": {"id": 99},
                "questions": [{"id": 1}],
            }
        assert "abc123" in url

        return _build_media_document()

    def get_text(self, url, send_cookie):
        """Return a play page that names the Wistia hashed ID."""

        assert send_cookie is True

        return '<script src="https://fast.wistia.com/embed/medias/abc123.jsonp"></script>'

    def download_file(self, url, destination_filepath, on_chunk, send_cookie=False):
        """Write the URL text and report a fixed length."""

        self.downloaded_urls.append(url)
        self.send_cookie_flags.append(send_cookie)
        self.progress_callback_ids.append(id(on_chunk))
        on_chunk(0, 4)
        with open(destination_filepath, "w", encoding="utf-8") as destination_file:
            destination_file.write("data")
        on_chunk(4, None)


class _RecordingProgress:
    """Counts byte-progress calls for non-playlist downloads."""

    def __init__(self):
        """Start with no calls."""

        self.call_count = 0

    def __call__(self, chunk_byte_count, content_length):
        """Count one progress report."""

        self.call_count = self.call_count + 1


def _ignore_operation(message):
    """Discard operation lines in unit tests."""

    return None


class _IgnoreResolveProgress:
    """Resolve progress that records nothing."""

    def advance(self, lesson_name):
        """Ignore one lesson."""

        return None

    def close(self):
        """Ignore close."""

        return None


def _open_ignore_resolve_progress(total):
    """Return a resolve progress that records nothing."""

    return _IgnoreResolveProgress()


_CONTENTABLE_ID_BY_CONTENT_ID = {
    11: 501,
    12: 502,
    21: 601,
    13: 701,
}
_SITE_HOST = "creatify.thinkific.com"


def test_collect_video_jobs_omits_lessons_without_video():
    """Only the lesson with a Wistia ID becomes a job, and the high bitrate file is chosen."""

    client = _FakePlayerClient()
    jobs, lessons_without_video = cggt.course.course_media.collect_video_jobs(
        client,
        _build_course_document(),
        _SITE_HOST,
        _CONTENTABLE_ID_BY_CONTENT_ID,
        _ignore_operation,
        _open_ignore_resolve_progress)

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
        {"content_id": 14, "lesson_name": "Not In Player", "reason": "missing contentable_id in course player (enrollment may be required)"},
    ]


def test_download_and_catalog_then_skip_and_merge(tmp_path):
    """Video files land under videos/{content_id}; a second run skips them."""

    output_directory_path = str(tmp_path)
    client = _FakePlayerClient()
    jobs, _lessons_without_video = cggt.course.course_media.collect_video_jobs(
        client,
        _build_course_document(),
        _SITE_HOST,
        _CONTENTABLE_ID_BY_CONTENT_ID,
        _ignore_operation,
        _open_ignore_resolve_progress)
    videos_directory_path = os.path.join(output_directory_path, cggt.course.course_media.VIDEOS_DIRECTORY_NAME)
    cggt.course.course_media.write_wistia_catalog(
        videos_directory_path,
        jobs,
        _ignore_operation)
    assert cggt.course.course_media.is_content_directory_present(
        output_directory_path,
        cggt.course.course_media.MEDIA_KIND_VIDEOS,
        11) is False
    recording_progress = _RecordingProgress()
    cggt.course.course_media.download_video_files(
        client,
        jobs[0],
        output_directory_path,
        recording_progress,
        _ignore_operation)
    assert recording_progress.call_count == 2
    assert client.progress_callback_ids[0] != id(recording_progress)
    assert client.progress_callback_ids[1] != id(recording_progress)
    assert client.progress_callback_ids[2] == id(recording_progress)
    content_directory_path = os.path.join(videos_directory_path, "11")
    assert os.path.isfile(os.path.join(content_directory_path, "playlist.m3u8"))
    assert os.path.isfile(os.path.join(content_directory_path, "video.mp4"))
    metadata = json.loads(open(os.path.join(content_directory_path, "metadata.json"), encoding="utf-8").read())
    assert metadata["content_id"] == 11
    assert metadata["content_specific"]["lesson_id"] == 501
    assert metadata["content_specific"]["video_id"] == 9
    assert metadata["content_specific"]["video_identifier"] == "proxy-id"
    assert metadata["content_specific"]["wistia_id"] == "abc123"
    assert cggt.course.course_media.is_content_directory_present(
        output_directory_path,
        cggt.course.course_media.MEDIA_KIND_VIDEOS,
        11) is True
    wistia_filepath = os.path.join(videos_directory_path, "wistia", "abc123.json")
    assert json.loads(open(wistia_filepath, encoding="utf-8").read())["media"]["assets"][0]["type"] == "hls_video"
    mapping_filepath = os.path.join(videos_directory_path, "wistia", "content_id_to_wistia_urls.json")
    mapping = json.loads(open(mapping_filepath, encoding="utf-8").read())
    assert mapping["11"][0] == "https://fast.wistia.net/embed/medias/abc123.m3u8"


def test_collect_and_download_pdf(tmp_path):
    """PDF jobs download into documents/{content_id}/document.pdf."""

    output_directory_path = str(tmp_path)
    client = _FakePlayerClient()
    jobs, skipped = cggt.course.course_media.collect_document_jobs(
        client,
        _build_course_document(),
        _SITE_HOST,
        _CONTENTABLE_ID_BY_CONTENT_ID,
        _ignore_operation)

    assert skipped == []
    assert len(jobs) == 1
    assert jobs[0]["content_id"] == 21
    progress = _RecordingProgress()
    cggt.course.course_media.download_document_files(
        client,
        jobs[0],
        output_directory_path,
        progress,
        _ignore_operation)
    assert client.send_cookie_flags == [False]
    content_directory_path = os.path.join(
        output_directory_path,
        cggt.course.course_media.DOCUMENTS_DIRECTORY_NAME,
        "21")
    assert os.path.isfile(os.path.join(content_directory_path, "document.pdf"))
    metadata = json.loads(open(os.path.join(content_directory_path, "metadata.json"), encoding="utf-8").read())
    assert metadata["content_specific"]["pdf_id"] == 88
    assert metadata["content_specific"]["source_url"] == "https://cdn.example/handbook.pdf"


def test_collect_and_write_quiz(tmp_path):
    """Quiz jobs write quiz.json under quizzes/{content_id}/."""

    output_directory_path = str(tmp_path)
    client = _FakePlayerClient()
    jobs, skipped = cggt.course.course_media.collect_quiz_jobs(
        client,
        _build_course_document(),
        _SITE_HOST,
        _CONTENTABLE_ID_BY_CONTENT_ID,
        _ignore_operation)

    assert skipped == []
    assert len(jobs) == 1
    cggt.course.course_media.download_quiz_files(
        client,
        jobs[0],
        output_directory_path,
        _ignore_operation)
    content_directory_path = os.path.join(
        output_directory_path,
        cggt.course.course_media.QUIZZES_DIRECTORY_NAME,
        "13")
    quiz_payload = json.loads(open(os.path.join(content_directory_path, "quiz.json"), encoding="utf-8").read())
    assert quiz_payload["quiz"]["id"] == 99
    metadata = json.loads(open(os.path.join(content_directory_path, "metadata.json"), encoding="utf-8").read())
    assert metadata["content_specific"]["question_count"] == 1
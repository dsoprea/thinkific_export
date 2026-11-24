"""Course media URL selection and on-disk layout."""

import json
import os

import pytest

import cggt.course.course_media
import cggt.course.player_client


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


class _UnplayableLessonClient:
    """Returns a play page with no Wistia media for the second lesson."""

    def get_json(self, url, send_cookie):
        """Return the course player payloads, one of them unplayable."""

        if url.endswith("/courses/demo"):
            return {
                "contents": [
                    {"id": 11, "contentable_type": "Lesson", "contentable_id": 501},
                    {"id": 12, "contentable_type": "Lesson", "contentable_id": 502},
                ],
            }
        if url.endswith("/lessons/501"):
            return {
                "lesson": {"video_id": 9, "video_url": "https://creatify.thinkific.com/play/11"},
                "videos": [{"id": 9, "identifier": "proxy-id"}],
            }
        if url.endswith("/lessons/502"):
            return {
                "lesson": {"video_id": 10, "video_url": "https://creatify.thinkific.com/play/12"},
                "videos": [],
            }
        assert "abc123" in url

        return _build_media_document()

    def get_text(self, url, send_cookie):
        """Return the Wistia play page for the first lesson and a sign-in wall for the second."""

        if url.endswith("/play/11"):
            return '<script src="https://fast.wistia.com/embed/medias/abc123.jsonp"></script>'

        return "<html><body>Sign in to continue</body></html>"


def test_collect_video_jobs_lists_a_lesson_whose_play_page_has_no_wistia_media():
    """One unplayable lesson is listed, and the lessons after it still become jobs."""

    jobs, lessons_without_video = cggt.course.course_media.collect_video_jobs(
        _UnplayableLessonClient(),
        _build_course_document(),
        _SITE_HOST,
        _CONTENTABLE_ID_BY_CONTENT_ID,
        _ignore_operation,
        _open_ignore_resolve_progress)

    assert [job["content_id"] for job in jobs] == [11]
    assert lessons_without_video == [
        {"content_id": 12, "lesson_name": "No Video", "reason": "play page has no Wistia media"},
        {
            "content_id": 14,
            "lesson_name": "Not In Player",
            "reason": "missing contentable_id in course player (enrollment may be required)",
        },
    ]


class _LessonPayloadWithoutLessonObjectClient:
    """Returns a lesson payload that has no lesson object at all."""

    def get_json(self, url, send_cookie):
        """Return the course player payloads, one of them empty."""

        if url.endswith("/courses/demo"):
            return {"contents": [{"id": 11, "contentable_type": "Lesson", "contentable_id": 501}]}
        if url.endswith("/lessons/501"):
            return {}

        raise AssertionError("unexpected URL " + url)

    def get_text(self, url, send_cookie):
        """Return a play page, which this client must never be asked for."""

        raise AssertionError("unexpected play page fetch " + url)


def test_collect_video_jobs_lists_a_lesson_with_no_lesson_object():
    """A changed payload shape is a lesson without a video, not the end of the export."""

    jobs, lessons_without_video = cggt.course.course_media.collect_video_jobs(
        _LessonPayloadWithoutLessonObjectClient(),
        _build_course_document(),
        _SITE_HOST,
        {11: 501},
        _ignore_operation,
        _open_ignore_resolve_progress)

    assert jobs == []
    assert lessons_without_video == [
        {"content_id": 11, "lesson_name": "With Video"},
        {
            "content_id": 12,
            "lesson_name": "No Video",
            "reason": "missing contentable_id in course player (enrollment may be required)",
        },
        {
            "content_id": 14,
            "lesson_name": "Not In Player",
            "reason": "missing contentable_id in course player (enrollment may be required)",
        },
    ]


class _ShortBodyClient(_FakePlayerClient):
    """A player client whose downloads end before the length they declared."""

    def download_file(self, url, destination_filepath, on_chunk, send_cookie=False):
        """Write part of the body, then report the transfer as cut short."""

        on_chunk(0, 4096)
        with open(destination_filepath, "w", encoding="utf-8") as destination_file:
            destination_file.write("data")
        on_chunk(4, None)

        raise cggt.course.player_client.IncompleteDownloadError(
            "{url} gave 4 of 4096 bytes".format(url=url))


def test_download_video_files_leaves_no_content_directory_when_a_file_is_cut_short(tmp_path):
    """A cut-short download leaves nothing behind, so the next run downloads that content again."""

    output_directory_path = str(tmp_path)
    client = _FakePlayerClient()
    jobs, _lessons_without_video = cggt.course.course_media.collect_video_jobs(
        client,
        _build_course_document(),
        _SITE_HOST,
        _CONTENTABLE_ID_BY_CONTENT_ID,
        _ignore_operation,
        _open_ignore_resolve_progress)

    with pytest.raises(cggt.course.player_client.IncompleteDownloadError, match="4 of 4096 bytes"):
        cggt.course.course_media.download_video_files(
            _ShortBodyClient(),
            jobs[0],
            output_directory_path,
            _RecordingProgress(),
            _ignore_operation)

    assert os.path.isdir(os.path.join(output_directory_path, "videos", "11")) is False
    assert cggt.course.course_media.is_content_directory_present(
        output_directory_path,
        cggt.course.course_media.MEDIA_KIND_VIDEOS,
        11) is False


def test_build_download_filename_steps_past_a_numbered_name_already_taken():
    """A duplicate URL never takes a name another URL already has, whatever the order."""

    used_names = set()
    video_urls = [
        "https://cdn.example/one/a.m3u8",
        "https://cdn.example/two/a.m3u8",
        "https://cdn.example/three/3-a.m3u8",
        "https://cdn.example/four/a.m3u8",
    ]
    filenames = [
        cggt.course.course_media._build_download_filename(video_url, used_names)
        for video_url in video_urls
    ]

    assert filenames == ["a.m3u8", "1-a.m3u8", "3-a.m3u8", "4-a.m3u8"]

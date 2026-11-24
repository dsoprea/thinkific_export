"""cggt_export_course_media stderr progress, flags, and skip."""

import json
import os

import cggt.entrypoint.cggt_export_course_media


def _load_course_player_context(player_client, course_document, report_operation):
    """Return a fixed player context for tests."""

    return (
        "creatify.thinkific.com",
        "demo",
        {},
        {11: 501, 12: 502},
    )


def _collect_video_jobs(
        player_client,
        course_document,
        site_host,
        contentable_id_by_content_id,
        report_operation,
        open_resolve_progress):
    """Return one video job and one lesson without video."""

    return (
        [{
            "content_id": 11,
            "lesson_name": "With Video",
            "wistia_id": "abc123",
            "media_document": {"media": {"assets": []}},
            "video_urls": ["https://cdn.example/high.mp4"],
            "downloads": [{"url": "https://cdn.example/high.mp4", "filename": "video.mp4"}],
        }],
        [{"content_id": 12, "lesson_name": "No Video"}],
    )


def _download_video_files(player_client, job, output_directory_path, progress, report_operation):
    """Write one file and advance the bar."""

    progress(0, 3)
    content_directory_path = os.path.join(
        output_directory_path,
        "videos",
        "11")
    os.makedirs(content_directory_path)
    with open(os.path.join(content_directory_path, "video.mp4"), "w", encoding="utf-8") as output_file:
        output_file.write("mp4")
    progress(3, None)


def _collect_document_jobs(
        player_client,
        course_document,
        site_host,
        contentable_id_by_content_id,
        report_operation):
    """Return no document jobs."""

    return [], []


def _collect_quiz_jobs(
        player_client,
        course_document,
        site_host,
        contentable_id_by_content_id,
        report_operation):
    """Return no quiz jobs."""

    return [], []


def test_main_videos_only_prints_count_and_skips_existing(tmp_path, monkeypatch, capsys):
    """The bar description includes 1/1, and a second run skips the download."""

    session_filepath = os.path.join(str(tmp_path), "session.json")
    course_filepath = os.path.join(str(tmp_path), "course.json")
    output_directory_path = os.path.join(str(tmp_path), "out")
    os.makedirs(output_directory_path)
    with open(session_filepath, "w", encoding="utf-8") as session_file:
        json.dump({"cookie_header": "session=abc"}, session_file)
    with open(course_filepath, "w", encoding="utf-8") as course_file:
        json.dump({"course": {"slug": "demo"}, "chapters": []}, course_file)
    monkeypatch.setattr(
        cggt.entrypoint.cggt_export_course_media.cggt.course.course_media,
        "load_course_player_context",
        _load_course_player_context)
    monkeypatch.setattr(
        cggt.entrypoint.cggt_export_course_media.cggt.course.course_media,
        "collect_video_jobs",
        _collect_video_jobs)
    monkeypatch.setattr(
        cggt.entrypoint.cggt_export_course_media.cggt.course.course_media,
        "download_video_files",
        _download_video_files)
    monkeypatch.setattr(
        cggt.entrypoint.cggt_export_course_media.cggt.course.course_media,
        "collect_document_jobs",
        _collect_document_jobs)
    monkeypatch.setattr(
        cggt.entrypoint.cggt_export_course_media.cggt.course.course_media,
        "collect_quiz_jobs",
        _collect_quiz_jobs)
    exit_code = cggt.entrypoint.cggt_export_course_media.main([
        session_filepath,
        course_filepath,
        output_directory_path,
        "--videos",
    ])
    first = capsys.readouterr()
    assert exit_code == 0
    assert "reading " in first.err
    assert "lesson 12 No Video has no video" in first.err
    assert "writing " in first.err
    assert "1/1 With Video" in first.err
    exit_code = cggt.entrypoint.cggt_export_course_media.main([
        session_filepath,
        course_filepath,
        output_directory_path,
        "--videos",
    ])
    second = capsys.readouterr()

    assert exit_code == 0
    assert "skipping content ID 11" in second.err


def test_resolve_enabled_media_kinds_defaults_to_all():
    """When no kind flags are set, all three kinds are enabled."""

    class _Arguments:
        """Minimal namespace for flag resolution."""

        videos = False
        quizzes = False
        documents = False

    enabled = cggt.entrypoint.cggt_export_course_media._resolve_enabled_media_kinds(_Arguments())

    assert enabled == {
        cggt.course.course_media.MEDIA_KIND_VIDEOS,
        cggt.course.course_media.MEDIA_KIND_DOCUMENTS,
        cggt.course.course_media.MEDIA_KIND_QUIZZES,
    }
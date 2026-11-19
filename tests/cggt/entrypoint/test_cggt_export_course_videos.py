"""cggt_export_course_videos stderr progress and skip."""

import json
import os

import cggt.entrypoint.cggt_export_course_videos


def _collect_one_job(player_client, course_document, report_operation):
    """Return one video job and one lesson without video."""

    return (
        [{
            "content_id": 11,
            "lesson_name": "With Video",
            "wistia_id": "abc123",
            "media_document": {"media": {"assets": []}},
            "video_urls": ["https://cdn.example/high.mp4"],
        }],
        [{"content_id": 12, "lesson_name": "No Video"}],
    )


def _download_file(player_client, job, output_directory_path, progress, report_operation):
    """Write one file and advance the bar."""

    progress(0, 3)
    content_directory_path = os.path.join(output_directory_path, "11")
    os.makedirs(content_directory_path)
    with open(os.path.join(content_directory_path, "high.mp4"), "w", encoding="utf-8") as output_file:
        output_file.write("mp4")
    progress(3, None)


def test_main_prints_count_and_skips_existing(tmp_path, monkeypatch, capsys):
    """The bar description includes 1/1, and a second run skips the download."""

    session_filepath = os.path.join(str(tmp_path), "session.json")
    course_filepath = os.path.join(str(tmp_path), "course.json")
    output_directory_path = os.path.join(str(tmp_path), "out")
    os.makedirs(output_directory_path)
    with open(session_filepath, "w", encoding="utf-8") as session_file:
        json.dump({"cookie_header": "session=abc"}, session_file)
    with open(course_filepath, "w", encoding="utf-8") as course_file:
        json.dump({"chapters": []}, course_file)
    monkeypatch.setattr(
        cggt.entrypoint.cggt_export_course_videos.cggt.course.lesson_videos,
        "collect_lesson_video_jobs",
        _collect_one_job)
    monkeypatch.setattr(
        cggt.entrypoint.cggt_export_course_videos.cggt.course.lesson_videos,
        "download_lesson_files",
        _download_file)
    exit_code = cggt.entrypoint.cggt_export_course_videos.main([
        session_filepath,
        course_filepath,
        output_directory_path,
    ])
    first = capsys.readouterr()
    assert exit_code == 0
    assert "reading " in first.err
    assert "lesson 12 No Video has no video" in first.err
    assert "writing " in first.err
    assert "1/1 With Video" in first.err
    exit_code = cggt.entrypoint.cggt_export_course_videos.main([
        session_filepath,
        course_filepath,
        output_directory_path,
    ])
    second = capsys.readouterr()

    assert exit_code == 0
    assert "skipping content ID 11" in second.err

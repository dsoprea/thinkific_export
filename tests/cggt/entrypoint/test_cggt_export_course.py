"""cggt_export_course JSON stdout."""

import json

import cggt.entrypoint.cggt_export_course


def _load_course_content_document(thinkific_client, course_id, chapter_progress=None):
    """Return a fixed document for course 9."""

    assert course_id == 9

    return {
        "course": {"id": 9, "name": "Course"},
        "chapters": [],
    }


def test_main_writes_json_document(monkeypatch, capsys):
    """Stdout is the content document and stderr stays empty."""

    monkeypatch.setenv("THINKIFIC_API_ACCESS_TOKEN", "token-value")
    monkeypatch.setenv("THINKIFIC_SSO_SIGNING_SECRET", "secret-value")
    monkeypatch.setattr(
        cggt.entrypoint.cggt_export_course.cggt.course.catalog,
        "load_course_content_document",
        _load_course_content_document)
    exit_code = cggt.entrypoint.cggt_export_course.main(["9"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out)["course"]["id"] == 9

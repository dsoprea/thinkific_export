"""cggt_course_list stderr table."""

import cggt.entrypoint.cggt_course_list


def _load_course_list_rows(thinkific_client):
    """Return two rows already ordered by name."""

    return [
        {"id": 3, "name": "Alpha", "created_at": "2024-01-01T00:00:00Z"},
        {"id": 4, "name": "Beta", "created_at": "2024-02-02T00:00:00Z"},
    ]


def test_main_writes_sorted_table(monkeypatch, capsys):
    """The table headers and one data row go to stderr."""

    monkeypatch.setenv("THINKIFIC_API_ACCESS_TOKEN", "token-value")
    monkeypatch.setenv("THINKIFIC_SSO_SIGNING_SECRET", "secret-value")
    monkeypatch.setattr(
        cggt.entrypoint.cggt_course_list.cggt.course.catalog,
        "load_course_list_rows",
        _load_course_list_rows)
    exit_code = cggt.entrypoint.cggt_course_list.main([])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == ""
    assert "ID" in captured.err
    assert "Name" in captured.err
    assert "Created At" in captured.err
    assert "Alpha" in captured.err
    assert captured.err.index("Alpha") < captured.err.index("Beta")

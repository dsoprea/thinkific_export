"""Course list rows and content documents."""

import cggt.course.catalog


class _CatalogClient:
    """In-memory Thinkific responses keyed by path."""

    def __init__(self, collections, objects):
        """Store collection lists and single-object GETs."""

        self._collections = collections
        self._objects = objects
        self.collection_paths = []

    def list_collection(self, resource_path, query_items):
        """Return the canned collection for a path."""

        self.collection_paths.append(resource_path)

        return list(self._collections[resource_path])

    def get_json(self, resource_path, query_items):
        """Return the canned object for a path."""

        return self._objects[resource_path]


def test_load_course_list_rows_sorts_by_name_and_uses_product_created_at():
    """Names sort case-insensitively and timestamps come from the product."""

    client = _CatalogClient(
        collections={
            "/courses": [
                {"id": 2, "name": "zeta", "product_id": 20},
                {"id": 1, "name": "Alpha", "product_id": 10},
            ],
            "/products": [
                {"id": 20, "created_at": "2020-01-02T00:00:00Z"},
                {"id": 10, "created_at": "2020-01-01T00:00:00Z"},
            ],
        },
        objects={})
    rows = cggt.course.catalog.load_course_list_rows(client)

    assert rows == [
        {"id": 1, "name": "Alpha", "created_at": "2020-01-01T00:00:00Z"},
        {"id": 2, "name": "zeta", "created_at": "2020-01-02T00:00:00Z"},
    ]


def test_load_course_list_rows_keeps_a_course_whose_product_is_missing():
    """A course with no product row is listed with a blank created-at, not dropped or fatal."""

    client = _CatalogClient(
        collections={
            "/courses": [
                {"id": 2, "name": "zeta", "product_id": 20},
                {"id": 1, "name": "Alpha", "product_id": 10},
            ],
            "/products": [
                {"id": 10, "created_at": "2020-01-01T00:00:00Z"},
            ],
        },
        objects={})
    rows = cggt.course.catalog.load_course_list_rows(client)

    assert rows == [
        {"id": 1, "name": "Alpha", "created_at": "2020-01-01T00:00:00Z"},
        {"id": 2, "name": "zeta", "created_at": None},
    ]


def test_load_course_content_document_orders_chapters_and_contents():
    """Chapters and contents are nested and ordered by position."""

    client = _CatalogClient(
        collections={
            "/chapters/7/contents": [
                {"id": 70, "name": "later", "position": 2},
                {"id": 71, "name": "earlier", "position": 0},
            ],
            "/chapters/3/contents": [
                {"id": 30, "name": "only", "position": 0},
            ],
        },
        objects={
            "/courses/9": {
                "id": 9,
                "name": "Course",
                "chapter_ids": [7, 3],
            },
            "/chapters/7": {"id": 7, "name": "Second", "position": 2, "content_ids": [70, 71]},
            "/chapters/3": {"id": 3, "name": "First", "position": 0, "content_ids": [30]},
        })
    document = cggt.course.catalog.load_course_content_document(client, 9)

    assert document["course"]["id"] == 9
    assert [node["chapter"]["id"] for node in document["chapters"]] == [3, 7]
    assert [item["id"] for item in document["chapters"][1]["contents"]] == [71, 70]


class _RecordingChapterProgress:
    """Records begin, advance, and close calls."""

    def __init__(self):
        """Start empty."""

        self.total = None
        self.labels = []
        self.closed = False

    def begin(self, total):
        """Store the total step count."""

        self.total = total

    def advance(self, label):
        """Append one label."""

        self.labels.append(label)

    def close(self):
        """Mark the bar closed."""

        self.closed = True


def test_load_course_content_document_reports_chapter_progress():
    """Progress advances once for the course and once per chapter in sort order."""

    client = _CatalogClient(
        collections={
            "/chapters/7/contents": [{"id": 70, "name": "only", "position": 0}],
            "/chapters/3/contents": [{"id": 30, "name": "solo", "position": 0}],
        },
        objects={
            "/courses/9": {"id": 9, "name": "Course", "chapter_ids": [7, 3]},
            "/chapters/7": {"id": 7, "name": "Second", "position": 2},
            "/chapters/3": {"id": 3, "name": "First", "position": 0},
        })
    chapter_progress = _RecordingChapterProgress()
    cggt.course.catalog.load_course_content_document(client, 9, chapter_progress)

    assert chapter_progress.total == 3
    assert chapter_progress.labels == ["course", "First", "Second"]
    assert chapter_progress.closed is True

"""Course list rows and full course content documents."""

import cggt.course.thinkific_client


def _build_sort_key_for_name(record):
    """Case-insensitive name used to order courses."""

    return record["name"].casefold()


def _build_sort_key_for_position(record):
    """Chapter or content order, then ID when positions tie."""

    return (record["position"], record["id"])


def load_course_list_rows(thinkific_client):
    """Return course ID, name, and product created-at, sorted by name.

    Course objects from ``GET /courses`` have no timestamps. ``created_at`` comes from
    the product whose ID is ``course["product_id"]``.
    """

    # Load both collections, then attach each course's product timestamp.
    course_records = thinkific_client.list_collection("/courses", [])
    product_records = thinkific_client.list_collection("/products", [])
    products_by_id = {}
    for product_record in product_records:
        products_by_id[product_record["id"]] = product_record
    rows = []
    for course_record in course_records:
        product_id = course_record["product_id"]
        product_record = products_by_id[product_id]
        row = {
            "id": course_record["id"],
            "name": course_record["name"],
            "created_at": product_record["created_at"],
        }
        rows.append(row)
    rows.sort(key=_build_sort_key_for_name)

    return rows


def load_course_content_document(thinkific_client, course_id):
    """Return the course, each chapter, and that chapter's contents.

    Chapters and contents keep the Thinkific JSON and are ordered by ``position``.
    """

    # Course first, then one chapter GET and one contents collection per chapter.
    course_record = thinkific_client.get_json(
        "/courses/{course_id}".format(course_id=course_id),
        [])
    chapter_records = []
    for chapter_id in course_record["chapter_ids"]:
        chapter_path = "/chapters/{chapter_id}".format(chapter_id=chapter_id)
        chapter_record = thinkific_client.get_json(chapter_path, [])
        chapter_records.append(chapter_record)
    chapter_records.sort(key=_build_sort_key_for_position)
    chapters = []
    for chapter_record in chapter_records:
        contents_path = "/chapters/{chapter_id}/contents".format(chapter_id=chapter_record["id"])
        content_records = thinkific_client.list_collection(contents_path, [])
        content_records.sort(key=_build_sort_key_for_position)
        chapter_node = {
            "chapter": chapter_record,
            "contents": content_records,
        }
        chapters.append(chapter_node)
    document = {
        "course": course_record,
        "chapters": chapters,
    }

    return document

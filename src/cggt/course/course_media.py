"""Download course videos, PDF documents, and quizzes from the Thinkific course player."""

import json
import os
import re
import shutil
import tempfile
import urllib.parse

VIDEOS_DIRECTORY_NAME = "videos"
DOCUMENTS_DIRECTORY_NAME = "documents"
QUIZZES_DIRECTORY_NAME = "quizzes"
WISTIA_DIRECTORY_NAME = "wistia"
WISTIA_MAPPING_FILENAME = "content_id_to_wistia_urls.json"
WISTIA_MEDIA_URL_FORMAT = "https://fast.wistia.com/embed/medias/{wistia_id}.json"
WISTIA_PLAYLIST_URL_FORMAT = "https://fast.wistia.net/embed/medias/{wistia_id}.m3u8"
_COURSE_PLAYER_COURSE_URL_FORMAT = "https://{host}/api/course_player/v2/courses/{slug}"
_COURSE_PLAYER_RESOURCE_URL_FORMAT = "https://{host}/api/course_player/v2/{segment}/{contentable_id}"
_WISTIA_HASHED_ID_PATTERN = re.compile(r"embed/medias/([A-Za-z0-9]+)\.jsonp")
_PROGRESSIVE_ASSET_TYPES = (
    "mp4_video",
    "md_mp4_video",
    "hd_mp4_video",
    "iphone_video",
    "original",
    "mp4",
)
_PLAYER_PATH_SEGMENT_BY_CONTENTABLE_TYPE = {
    "Lesson": "lessons",
    "Pdf": "pdfs",
    "Quiz": "quizzes",
}
MEDIA_KIND_VIDEOS = "videos"
MEDIA_KIND_DOCUMENTS = "documents"
MEDIA_KIND_QUIZZES = "quizzes"
_CONTENTABLE_TYPE_BY_MEDIA_KIND = {
    MEDIA_KIND_VIDEOS: "Lesson",
    MEDIA_KIND_DOCUMENTS: "Pdf",
    MEDIA_KIND_QUIZZES: "Quiz",
}
_OUTPUT_DIRECTORY_NAME_BY_MEDIA_KIND = {
    MEDIA_KIND_VIDEOS: VIDEOS_DIRECTORY_NAME,
    MEDIA_KIND_DOCUMENTS: DOCUMENTS_DIRECTORY_NAME,
    MEDIA_KIND_QUIZZES: QUIZZES_DIRECTORY_NAME,
}


class CourseMediaExportError(Exception):
    """The course export cannot be resolved into downloadable media."""


def load_course_player_context(player_client, course_document, report_operation):
    """Return site host, slug, course payload, and content ID to contentable ID map."""

    site_host, course_slug = _read_site_host_and_slug(course_document)
    course_url = _COURSE_PLAYER_COURSE_URL_FORMAT.format(host=site_host, slug=course_slug)
    report_operation("GET {url}".format(url=course_url))
    course_payload = player_client.get_json(course_url, True)
    contentable_id_by_content_id = _build_contentable_id_by_content_id(course_payload)

    return site_host, course_slug, course_payload, contentable_id_by_content_id


def collect_video_jobs(
        player_client,
        course_document,
        site_host,
        contentable_id_by_content_id,
        report_operation,
        open_resolve_progress):
    """Return video jobs and lessons that have no Wistia video."""

    # Map export lessons to lesson player payloads and Wistia assets.
    jobs = []
    lessons_without_video = []
    lesson_contents = list(_iterate_contents_by_contentable_type(course_document, "Lesson"))
    resolve_progress = open_resolve_progress(len(lesson_contents))
    try:
        for content_record in lesson_contents:
            content_id = content_record["id"]
            lesson_name = content_record["name"]
            contentable_id = _read_contentable_id_for_content(
                content_id,
                contentable_id_by_content_id)
            if contentable_id is None:
                lessons_without_video.append({
                    "content_id": content_id,
                    "lesson_name": lesson_name,
                    "reason": "missing contentable_id in course player (enrollment may be required)",
                })
                resolve_progress.advance(lesson_name)

                continue
            lesson_url = _COURSE_PLAYER_RESOURCE_URL_FORMAT.format(
                host=site_host,
                segment="lessons",
                contentable_id=contentable_id)
            lesson_payload = player_client.get_json(lesson_url, True)
            play_url = _read_play_url(lesson_payload)
            if play_url is None:
                lessons_without_video.append({
                    "content_id": content_id,
                    "lesson_name": lesson_name,
                })
                resolve_progress.advance(lesson_name)

                continue
            play_html = player_client.get_text(play_url, True)
            wistia_id = _read_wistia_hashed_id(play_html)
            if wistia_id is None:
                # A play page that is a sign-in wall, or a lesson embedded from another player, has
                # nothing to download. Listing it keeps the lessons after it in the export.
                lessons_without_video.append({
                    "content_id": content_id,
                    "lesson_name": lesson_name,
                    "reason": "play page has no Wistia media",
                })
                resolve_progress.advance(lesson_name)

                continue
            media_url = WISTIA_MEDIA_URL_FORMAT.format(wistia_id=wistia_id)
            media_document = player_client.get_json(media_url, False)
            playlist_urls, progressive_url = _select_video_urls(media_document)
            playlist_url = WISTIA_PLAYLIST_URL_FORMAT.format(wistia_id=wistia_id)
            if playlist_url not in playlist_urls:
                playlist_urls.insert(0, playlist_url)
            video_urls = list(playlist_urls)
            downloads = []
            used_names = set()
            for playlist in playlist_urls:
                downloads.append({
                    "url": playlist,
                    "filename": _build_download_filename(playlist, used_names),
                })
            if progressive_url is not None:
                video_urls.append(progressive_url)
                downloads.append({
                    "url": progressive_url,
                    "filename": "video.mp4",
                })
            video_id, video_identifier = _read_video_ids(lesson_payload)
            chapter_id = _read_chapter_id(content_record)
            jobs.append({
                "content_id": content_id,
                "name": lesson_name,
                "contentable_type": "Lesson",
                "contentable_id": contentable_id,
                "chapter_id": chapter_id,
                "lesson_id": contentable_id,
                "lesson_name": lesson_name,
                "video_id": video_id,
                "video_identifier": video_identifier,
                "wistia_id": wistia_id,
                "media_document": media_document,
                "video_urls": video_urls,
                "downloads": downloads,
            })
            resolve_progress.advance(lesson_name)
    finally:
        resolve_progress.close()

    return jobs, lessons_without_video


def collect_document_jobs(
        player_client,
        course_document,
        site_host,
        contentable_id_by_content_id,
        report_operation):
    """Return PDF document jobs and rows that could not be resolved."""

    jobs = []
    skipped = []
    pdf_contents = list(_iterate_contents_by_contentable_type(course_document, "Pdf"))
    for content_record in pdf_contents:
        content_id = content_record["id"]
        name = content_record["name"]
        contentable_id = _read_contentable_id_for_content(
            content_id,
            contentable_id_by_content_id)
        if contentable_id is None:
            skipped.append({
                "content_id": content_id,
                "name": name,
                "reason": "missing contentable_id in course player (enrollment may be required)",
            })

            continue
        pdf_url = _COURSE_PLAYER_RESOURCE_URL_FORMAT.format(
            host=site_host,
            segment="pdfs",
            contentable_id=contentable_id)
        report_operation("GET {url}".format(url=pdf_url))
        player_payload = player_client.get_json(pdf_url, True)
        try:
            pdf_record = player_payload["pdf"]
        except KeyError as error:
            raise CourseMediaExportError(
                "pdf player response for content ID {content_id} has no pdf object".format(
                    content_id=content_id)) from error
        try:
            download_url = pdf_record["url"]
        except KeyError as error:
            skipped.append({
                "content_id": content_id,
                "name": name,
                "reason": "pdf object has no url",
            })

            continue
        if download_url is None or download_url == "":
            skipped.append({
                "content_id": content_id,
                "name": name,
                "reason": "pdf url is empty",
            })

            continue
        chapter_id = _read_chapter_id(content_record)
        jobs.append({
            "content_id": content_id,
            "name": name,
            "contentable_type": "Pdf",
            "contentable_id": contentable_id,
            "chapter_id": chapter_id,
            "player_payload": player_payload,
            "download_url": download_url,
            "pdf_id": pdf_record["id"],
            "downloadable": pdf_record.get("downloadable"),
        })

    return jobs, skipped


def collect_quiz_jobs(
        player_client,
        course_document,
        site_host,
        contentable_id_by_content_id,
        report_operation):
    """Return quiz jobs and rows that could not be resolved."""

    jobs = []
    skipped = []
    quiz_contents = list(_iterate_contents_by_contentable_type(course_document, "Quiz"))
    for content_record in quiz_contents:
        content_id = content_record["id"]
        name = content_record["name"]
        contentable_id = _read_contentable_id_for_content(
            content_id,
            contentable_id_by_content_id)
        if contentable_id is None:
            skipped.append({
                "content_id": content_id,
                "name": name,
                "reason": "missing contentable_id in course player (enrollment may be required)",
            })

            continue
        quiz_url = _COURSE_PLAYER_RESOURCE_URL_FORMAT.format(
            host=site_host,
            segment="quizzes",
            contentable_id=contentable_id)
        report_operation("GET {url}".format(url=quiz_url))
        player_payload = player_client.get_json(quiz_url, True)
        try:
            quiz_record = player_payload["quiz"]
        except KeyError as error:
            raise CourseMediaExportError(
                "quiz player response for content ID {content_id} has no quiz object".format(
                    content_id=content_id)) from error
        questions = player_payload.get("questions")
        if questions is None:
            questions = []
        chapter_id = _read_chapter_id(content_record)
        jobs.append({
            "content_id": content_id,
            "name": name,
            "contentable_type": "Quiz",
            "contentable_id": contentable_id,
            "chapter_id": chapter_id,
            "player_payload": player_payload,
            "quiz_id": quiz_record["id"],
            "question_count": len(questions),
        })

    return jobs, skipped


def write_wistia_catalog(videos_directory_path, jobs, report_operation):
    """Replace each Wistia media JSON and merge content-ID URL entries under videos/wistia/."""

    wistia_directory_path = os.path.join(videos_directory_path, WISTIA_DIRECTORY_NAME)
    os.makedirs(wistia_directory_path, exist_ok=True)
    for job in jobs:
        media_filepath = os.path.join(
            wistia_directory_path,
            "{wistia_id}.json".format(wistia_id=job["wistia_id"]))
        report_operation("writing {filepath}".format(filepath=media_filepath))
        _write_json(media_filepath, job["media_document"])
    mapping_filepath = os.path.join(wistia_directory_path, WISTIA_MAPPING_FILENAME)
    report_operation("reading {filepath}".format(filepath=mapping_filepath))
    mapping = _load_mapping(mapping_filepath)
    for job in jobs:
        mapping[str(job["content_id"])] = list(job["video_urls"])
    report_operation("writing {filepath}".format(filepath=mapping_filepath))
    _write_json(mapping_filepath, mapping)


def is_content_directory_present(output_directory_path, media_kind, content_id):
    """Return whether the content-ID directory under a media kind already holds files."""

    content_directory_path = build_content_directory_path(
        output_directory_path,
        media_kind,
        content_id)
    if not os.path.isdir(content_directory_path):
        return False
    names = os.listdir(content_directory_path)

    return len(names) > 0


def build_content_directory_path(output_directory_path, media_kind, content_id):
    """Return OUTPUT/{media_kind}/{content_id}/."""

    subdirectory_name = _OUTPUT_DIRECTORY_NAME_BY_MEDIA_KIND[media_kind]

    return os.path.join(output_directory_path, subdirectory_name, str(content_id))


def download_video_files(player_client, job, output_directory_path, progress, report_operation):
    """Download lesson video files into videos/{content_id}/."""

    content_directory_path = build_content_directory_path(
        output_directory_path,
        MEDIA_KIND_VIDEOS,
        job["content_id"])
    metadata_document = _build_metadata_document(
        job,
        {
            "lesson_id": job["lesson_id"],
            "video_id": job["video_id"],
            "video_identifier": job["video_identifier"],
            "wistia_id": job["wistia_id"],
        })
    _download_files_into_content_directory(
        player_client,
        job["downloads"],
        content_directory_path,
        metadata_document,
        progress,
        report_operation)


def download_document_files(player_client, job, output_directory_path, progress, report_operation):
    """Download one PDF into documents/{content_id}/ as document.ext."""

    extension = _read_extension_from_url(job["download_url"])
    filename = _format_indexed_basename("document", 0, extension)
    content_directory_path = build_content_directory_path(
        output_directory_path,
        MEDIA_KIND_DOCUMENTS,
        job["content_id"])
    metadata_document = _build_metadata_document(
        job,
        {
            "pdf_id": job["pdf_id"],
            "source_url": job["download_url"],
            "downloadable": job["downloadable"],
        })
    downloads = [{"url": job["download_url"], "filename": filename, "send_cookie": False}]
    _download_files_into_content_directory(
        player_client,
        downloads,
        content_directory_path,
        metadata_document,
        progress,
        report_operation)


def download_quiz_files(player_client, job, output_directory_path, report_operation):
    """Write quiz.json and metadata under quizzes/{content_id}/."""

    content_directory_path = build_content_directory_path(
        output_directory_path,
        MEDIA_KIND_QUIZZES,
        job["content_id"])
    temp_directory_path = tempfile.mkdtemp()
    try:
        quiz_filepath = os.path.join(temp_directory_path, _format_indexed_basename("quiz", 0, ".json"))
        report_operation("writing {filepath}".format(filepath=quiz_filepath))
        _write_json(quiz_filepath, job["player_payload"])
        metadata_document = _build_metadata_document(
            job,
            {
                "quiz_id": job["quiz_id"],
                "question_count": job["question_count"],
            })
        metadata_filepath = os.path.join(temp_directory_path, "metadata.json")
        report_operation("writing {filepath}".format(filepath=metadata_filepath))
        _write_json(metadata_filepath, metadata_document)
        if os.path.isdir(content_directory_path):
            shutil.rmtree(content_directory_path)
        report_operation("copying content ID {content_id} to {path}".format(
            content_id=job["content_id"],
            path=content_directory_path))
        shutil.copytree(temp_directory_path, content_directory_path)
    finally:
        shutil.rmtree(temp_directory_path)


def _download_files_into_content_directory(
        player_client,
        downloads,
        content_directory_path,
        metadata_document,
        progress,
        report_operation):
    """Download each URL to a temp tree, write metadata, then copy into place."""

    temp_directory_path = tempfile.mkdtemp()
    try:
        for download in downloads:
            destination_filepath = os.path.join(temp_directory_path, download["filename"])
            report_operation("downloading {url}".format(url=download["url"]))
            download_progress = progress
            if ".m3u8" in download["url"]:
                download_progress = _ignore_download_progress
            send_cookie = True
            try:
                send_cookie = download["send_cookie"]
            except KeyError:
                send_cookie = True
            player_client.download_file(
                download["url"],
                destination_filepath,
                download_progress,
                send_cookie)
        metadata_filepath = os.path.join(temp_directory_path, "metadata.json")
        report_operation("writing {filepath}".format(filepath=metadata_filepath))
        _write_json(metadata_filepath, metadata_document)
        if os.path.isdir(content_directory_path):
            shutil.rmtree(content_directory_path)
        report_operation("copying content ID {content_id} to {path}".format(
            content_id=metadata_document["content_id"],
            path=content_directory_path))
        shutil.copytree(temp_directory_path, content_directory_path)
    finally:
        shutil.rmtree(temp_directory_path)


def _build_metadata_document(job, content_specific):
    """Return shared metadata plus type-specific fields."""

    metadata_document = {
        "content_id": job["content_id"],
        "name": job["name"],
        "contentable_type": job["contentable_type"],
        "contentable_id": job["contentable_id"],
        "content_specific": content_specific,
    }
    # Include chapter ID when the export row had one.
    try:
        chapter_id = job["chapter_id"]
    except KeyError:
        chapter_id = None
    if chapter_id is not None:
        metadata_document["chapter_id"] = chapter_id

    return metadata_document


def _format_indexed_basename(base_name, file_index, extension):
    """Return document.pdf, document-1.pdf, quiz.json, quiz-1.json, etc."""

    if file_index == 0:
        return base_name + extension

    return "{base_name}-{file_index}{extension}".format(
        base_name=base_name,
        file_index=file_index,
        extension=extension)


def _read_extension_from_url(url):
    """Return a file extension from the URL path, or .pdf when absent."""

    parsed = urllib.parse.urlparse(url)
    _, extension = os.path.splitext(parsed.path)
    if extension == "":
        return ".pdf"

    return extension


def _read_chapter_id(content_record):
    """Return chapter_id when present on an export content row."""

    try:
        return content_record["chapter_id"]
    except KeyError:
        return None


def _read_contentable_id_for_content(content_id, contentable_id_by_content_id):
    """Return contentable ID for a content ID, or None when the player omitted it."""

    try:
        return contentable_id_by_content_id[content_id]
    except KeyError:
        return None


def _ignore_download_progress(chunk_byte_count, content_length):
    """Drop byte progress for M3U8 playlist files."""

    return None


def _iterate_contents_by_contentable_type(course_document, contentable_type):
    """Yield export contents of one contentable type in chapter order."""

    for chapter_node in course_document["chapters"]:
        for content_record in chapter_node["contents"]:
            if content_record["contentable_type"] == contentable_type:
                yield content_record


def _iterate_course_contents(course_document):
    """Yield every content row in chapter and position order."""

    for chapter_node in course_document["chapters"]:
        for content_record in chapter_node["contents"]:
            yield content_record


def _read_site_host_and_slug(course_document):
    """Return the site host and course slug from course metadata and take URLs."""

    course_record = course_document["course"]
    course_slug = course_record["slug"]
    for content_record in _iterate_course_contents(course_document):
        try:
            take_url = content_record["take_url"]
        except KeyError:
            continue
        parsed = urllib.parse.urlparse(take_url)
        marker = "/courses/take/"
        path = parsed.path
        marker_index = path.find(marker)
        if parsed.hostname is not None and marker_index >= 0:
            if course_slug != "":
                return parsed.hostname, course_slug
    message = "course export has no take_url under /courses/take/"

    raise CourseMediaExportError(message)


def _build_contentable_id_by_content_id(course_payload):
    """Map every content ID to its contentable ID from the course player payload."""

    contentable_id_by_content_id = {}
    for content_record in course_payload["contents"]:
        content_id = content_record["id"]
        contentable_id = content_record.get("contentable_id")
        if contentable_id is None:
            contentable_id = content_record.get("contentable")
        contentable_id_by_content_id[content_id] = contentable_id

    return contentable_id_by_content_id


def _read_play_url(lesson_payload):
    """Return the lesson play URL, or None when the lesson has no video."""

    # Every field here is the player's to omit: a lesson without a video, or one whose payload
    # changed shape, is listed as having no video rather than ending the export.
    lesson = lesson_payload.get("lesson")
    if lesson is None:
        return None
    video_id = lesson.get("video_id")
    if video_id is None:
        return None
    play_url = lesson.get("video_url")
    if play_url is None or play_url == "":
        return None

    return play_url


def _read_wistia_hashed_id(play_html):
    """Return the public Wistia hashed ID embedded in the play page, or None when it has none."""

    match = _WISTIA_HASHED_ID_PATTERN.search(play_html)
    if match is None:
        return None

    return match.group(1)


def _read_video_ids(lesson_payload):
    """Return the lesson video ID and the player video identifier."""

    video_id = lesson_payload["lesson"]["video_id"]
    video_identifier = None
    try:
        videos = lesson_payload["videos"]
    except KeyError:
        videos = []
    for video in videos:
        if video["id"] == video_id:
            video_identifier = video["identifier"]

            break

    return video_id, video_identifier


def _select_video_urls(media_document):
    """Return HLS playlist URLs and the highest-bitrate progressive asset URL."""

    playlist_urls = []
    progressive_url = None
    progressive_bitrate = None
    for asset in media_document["media"]["assets"]:
        asset_url = asset["url"]
        asset_type = asset["type"]
        if asset_type == "hls_video" or ".m3u8" in asset_url:
            playlist_urls.append(asset_url)
            continue
        if asset_type not in _PROGRESSIVE_ASSET_TYPES:
            continue
        try:
            bitrate = asset["bitrate"]
        except KeyError:
            bitrate = 0
        if progressive_bitrate is None or bitrate > progressive_bitrate:
            progressive_bitrate = bitrate
            progressive_url = asset_url

    return playlist_urls, progressive_url


def _load_mapping(mapping_filepath):
    """Load an existing content-ID mapping, or an empty object."""

    if not os.path.isfile(mapping_filepath):
        return {}
    with open(mapping_filepath, "r", encoding="utf-8") as mapping_file:
        mapping = json.load(mapping_file)

    return mapping


def _write_json(filepath, document):
    """Write JSON with sorted keys."""

    encoded = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
    with open(filepath, "w", encoding="utf-8") as output_file:
        output_file.write(encoded)
        output_file.write("\n")


def _build_download_filename(video_url, used_names):
    """Return a unique basename for a video URL inside one content directory."""

    parsed = urllib.parse.urlparse(video_url)
    filename = os.path.basename(parsed.path)
    if filename == "":
        filename = "download.bin"
    # The numbered name a duplicate URL is given can itself be the name another URL already took, so
    # test the name that is used rather than the one it started from: two files of one name would
    # overwrite each other in the content directory.
    candidate = filename
    file_index = len(used_names)
    while candidate in used_names:
        candidate = "{count}-{filename}".format(count=file_index, filename=filename)
        file_index = file_index + 1
    used_names.add(candidate)

    return candidate
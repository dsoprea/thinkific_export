"""Resolve lesson videos and write them under a content-ID directory."""

import json
import os
import re
import shutil
import tempfile
import urllib.parse

WISTIA_DIRECTORY_NAME = "wistia"
WISTIA_MAPPING_FILENAME = "content_id_to_wistia_urls.json"
WISTIA_MEDIA_URL_FORMAT = "https://fast.wistia.com/embed/medias/{wistia_id}.json"
WISTIA_PLAYLIST_URL_FORMAT = "https://fast.wistia.net/embed/medias/{wistia_id}.m3u8"
_COURSE_PLAYER_COURSE_URL_FORMAT = "https://{host}/api/course_player/v2/courses/{slug}"
_COURSE_PLAYER_LESSON_URL_FORMAT = "https://{host}/api/course_player/v2/lessons/{lesson_id}"
_WISTIA_HASHED_ID_PATTERN = re.compile(r"embed/medias/([A-Za-z0-9]+)\.jsonp")
_PROGRESSIVE_ASSET_TYPES = (
    "mp4_video",
    "md_mp4_video",
    "hd_mp4_video",
    "iphone_video",
    "original",
    "mp4",
)


class LessonVideoExportError(Exception):
    """The course export cannot be resolved into lesson videos."""


def collect_lesson_video_jobs(player_client, course_document, report_operation):
    """Return video jobs and lessons that have no Wistia video.

    Each job is a dict with ``content_id``, ``lesson_name``, ``wistia_id``,
    ``media_document``, and ``video_urls``.
    """

    # The course-player course payload maps each content ID to a lesson ID.
    site_host, course_slug = _read_site_host_and_slug(course_document)
    course_url = _COURSE_PLAYER_COURSE_URL_FORMAT.format(host=site_host, slug=course_slug)
    report_operation("GET {url}".format(url=course_url))
    course_payload = player_client.get_json(course_url, True)
    lesson_id_by_content_id = _build_lesson_id_by_content_id(course_payload)
    jobs = []
    lessons_without_video = []
    for content_record in _iterate_lesson_contents(course_document):
        content_id = content_record["id"]
        lesson_name = content_record["name"]
        try:
            lesson_id = lesson_id_by_content_id[content_id]
        except KeyError:
            lessons_without_video.append({
                "content_id": content_id,
                "lesson_name": lesson_name,
            })

            continue
        lesson_url = _COURSE_PLAYER_LESSON_URL_FORMAT.format(host=site_host, lesson_id=lesson_id)
        report_operation("GET {url}".format(url=lesson_url))
        lesson_payload = player_client.get_json(lesson_url, True)
        play_url = _read_play_url(lesson_payload)
        if play_url is None:
            lessons_without_video.append({
                "content_id": content_id,
                "lesson_name": lesson_name,
            })

            continue
        report_operation("GET {url}".format(url=play_url))
        play_html = player_client.get_text(play_url, True)
        wistia_id = _read_wistia_hashed_id(play_html, content_id)
        media_url = WISTIA_MEDIA_URL_FORMAT.format(wistia_id=wistia_id)
        report_operation("GET {url}".format(url=media_url))
        media_document = player_client.get_json(media_url, False)
        video_urls = _select_video_urls(media_document)
        playlist_url = WISTIA_PLAYLIST_URL_FORMAT.format(wistia_id=wistia_id)
        if playlist_url not in video_urls:
            video_urls.insert(0, playlist_url)
        jobs.append({
            "content_id": content_id,
            "lesson_name": lesson_name,
            "wistia_id": wistia_id,
            "media_document": media_document,
            "video_urls": video_urls,
        })

    return jobs, lessons_without_video


def write_wistia_catalog(output_directory_path, jobs, report_operation):
    """Replace each Wistia media JSON and merge content-ID URL entries."""

    # Catalog lives beside the content-ID directories and is rewritten every run.
    wistia_directory_path = os.path.join(output_directory_path, WISTIA_DIRECTORY_NAME)
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


def is_content_directory_present(output_directory_path, content_id):
    """Return whether the content-ID directory already holds files."""

    content_directory_path = os.path.join(output_directory_path, str(content_id))
    if not os.path.isdir(content_directory_path):
        return False
    names = os.listdir(content_directory_path)

    return len(names) > 0


def download_lesson_files(player_client, job, output_directory_path, progress, report_operation):
    """Download the job's URLs to a temp directory, then copy them into place."""

    # Keep the destination untouched until every file has been written.
    temp_directory_path = tempfile.mkdtemp()
    try:
        used_names = set()
        for video_url in job["video_urls"]:
            filename = _build_download_filename(video_url, used_names)
            destination_filepath = os.path.join(temp_directory_path, filename)
            report_operation("downloading {url}".format(url=video_url))
            player_client.download_file(
                video_url,
                destination_filepath,
                progress)
        content_directory_path = os.path.join(
            output_directory_path,
            str(job["content_id"]))
        if os.path.isdir(content_directory_path):
            os.rmdir(content_directory_path)
        report_operation("copying content ID {content_id} to {path}".format(
            content_id=job["content_id"],
            path=content_directory_path))
        shutil.copytree(temp_directory_path, content_directory_path)
    finally:
        shutil.rmtree(temp_directory_path)


def _iterate_lesson_contents(course_document):
    """Yield lesson content rows in chapter and position order."""

    for chapter_node in course_document["chapters"]:
        for content_record in chapter_node["contents"]:
            if content_record["contentable_type"] == "Lesson":
                yield content_record


def _read_site_host_and_slug(course_document):
    """Return the site host and course slug from the first lesson take URL."""

    for content_record in _iterate_lesson_contents(course_document):
        parsed = urllib.parse.urlparse(content_record["take_url"])
        marker = "/courses/take/"
        path = parsed.path
        marker_index = path.find(marker)
        if parsed.hostname is not None and marker_index >= 0:
            remainder = path[marker_index + len(marker):]
            slug = remainder.split("/", 1)[0]
            if slug != "":
                return parsed.hostname, slug
    message = "course export has no lesson take_url"

    raise LessonVideoExportError(message)


def _build_lesson_id_by_content_id(course_payload):
    """Map content ID to the lesson ``contentable_id``."""

    lesson_id_by_content_id = {}
    for content_record in course_payload["contents"]:
        if content_record["contentable_type"] != "Lesson":
            continue
        lesson_id_by_content_id[content_record["id"]] = content_record["contentable_id"]

    return lesson_id_by_content_id


def _read_play_url(lesson_payload):
    """Return the lesson play URL, or None when the lesson has no video."""

    lesson = lesson_payload["lesson"]
    try:
        video_id = lesson["video_id"]
    except KeyError:
        return None
    if video_id is None:
        return None
    play_url = lesson["video_url"]
    if play_url is None or play_url == "":
        return None

    return play_url


def _read_wistia_hashed_id(play_html, content_id):
    """Return the public Wistia hashed ID embedded in the play page."""

    match = _WISTIA_HASHED_ID_PATTERN.search(play_html)
    if match is None:
        message = "play page for content ID {content_id} has no Wistia media".format(
            content_id=content_id)

        raise LessonVideoExportError(message)

    return match.group(1)


def _select_video_urls(media_document):
    """Return HLS playlist URLs plus the highest-bitrate progressive asset."""

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
    video_urls = list(playlist_urls)
    if progressive_url is not None and progressive_url not in video_urls:
        video_urls.append(progressive_url)

    return video_urls


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
    if filename in used_names:
        filename = "{count}-{filename}".format(count=len(used_names), filename=filename)
    used_names.add(filename)

    return filename

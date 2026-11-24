"""Download course videos, PDFs, and quizzes from a course export."""

import argparse
import json
import os
import sys

import tqdm

import cggt.config.entrypoint.cggt_export_course_media
import cggt.course.course_media
import cggt.course.player_client


class _ResolveProgress:
    """One stderr bar for resolving every lesson video."""

    def __init__(self, total):
        """Open a bar whose total is the lesson count."""

        self._total = total
        self._number = 0
        self._bar = tqdm.tqdm(
            total=total,
            file=sys.stderr)

    def advance(self, lesson_name):
        """Move the bar one lesson and show its position and name."""

        self._number = self._number + 1
        description = "{number}/{total} {lesson_name}".format(
            number=self._number,
            total=self._total,
            lesson_name=lesson_name)
        self._bar.set_description(description)
        self._bar.update(1)

    def close(self):
        """Finish the bar."""

        self._bar.close()


def _open_resolve_progress(total):
    """Open the lesson-resolve bar."""

    return _ResolveProgress(total)


class _ByteProgress:
    """tqdm bar that grows its total as each file reports Content-Length."""

    def __init__(self, description):
        """Open one stderr bar for a single progressive download."""

        self._bar = tqdm.tqdm(
            desc=description,
            unit="B",
            unit_scale=True,
            file=sys.stderr)

    def __call__(self, chunk_byte_count, content_length):
        """Add ``content_length`` to the total, then advance by the chunk."""

        if content_length is not None:
            if self._bar.total is None:
                self._bar.total = content_length
            else:
                self._bar.total = self._bar.total + content_length
        if chunk_byte_count > 0:
            self._bar.update(chunk_byte_count)

    def close(self):
        """Finish the bar."""

        self._bar.close()


def main(argv=None):
    """Download videos, documents, and quizzes into typed subdirectories."""

    parser = argparse.ArgumentParser(
        prog=cggt.config.entrypoint.cggt_export_course_media.PROG_NAME,
        description="Download course media from a cggt_export_course JSON file.")
    parser.add_argument(
        "session_filepath",
        help="Cookietruck JSON session file. The cookie_header field is sent as the Cookie header.")
    parser.add_argument(
        "course_export_filepath",
        help="JSON file written by cggt_export_course.")
    parser.add_argument(
        "output_directory_path",
        help="Directory root for videos/, documents/, and quizzes/ content-ID trees.")
    parser.add_argument(
        "--videos",
        action="store_true",
        help="Download lesson videos. With no kind flag, every kind runs.")
    parser.add_argument(
        "--quizzes",
        action="store_true",
        help="Download quiz JSON. With no kind flag, every kind runs.")
    parser.add_argument(
        "--documents",
        action="store_true",
        help="Download PDF documents. With no kind flag, every kind runs.")
    parsed_arguments = parser.parse_args(argv)
    enabled_media_kinds = _resolve_enabled_media_kinds(parsed_arguments)
    _report_operation("reading {filepath}".format(filepath=parsed_arguments.session_filepath))
    session_document = _load_json(parsed_arguments.session_filepath)
    _report_operation("reading {filepath}".format(filepath=parsed_arguments.course_export_filepath))
    course_document = _load_json(parsed_arguments.course_export_filepath)
    player_client = cggt.course.player_client.PlayerClient(session_document["cookie_header"])
    site_host, _course_slug, _course_payload, contentable_id_by_content_id = \
        cggt.course.course_media.load_course_player_context(
            player_client,
            course_document,
            _report_operation)
    if cggt.course.course_media.MEDIA_KIND_VIDEOS in enabled_media_kinds:
        _run_video_export(
            player_client,
            course_document,
            site_host,
            contentable_id_by_content_id,
            parsed_arguments.output_directory_path)
    if cggt.course.course_media.MEDIA_KIND_DOCUMENTS in enabled_media_kinds:
        _run_document_export(
            player_client,
            course_document,
            site_host,
            contentable_id_by_content_id,
            parsed_arguments.output_directory_path)
    if cggt.course.course_media.MEDIA_KIND_QUIZZES in enabled_media_kinds:
        _run_quiz_export(
            player_client,
            course_document,
            site_host,
            contentable_id_by_content_id,
            parsed_arguments.output_directory_path)

    return 0


def _resolve_enabled_media_kinds(parsed_arguments):
    """Return the set of media kinds to download."""

    if parsed_arguments.videos or parsed_arguments.quizzes or parsed_arguments.documents:
        enabled_media_kinds = set()
        if parsed_arguments.videos:
            enabled_media_kinds.add(cggt.course.course_media.MEDIA_KIND_VIDEOS)
        if parsed_arguments.documents:
            enabled_media_kinds.add(cggt.course.course_media.MEDIA_KIND_DOCUMENTS)
        if parsed_arguments.quizzes:
            enabled_media_kinds.add(cggt.course.course_media.MEDIA_KIND_QUIZZES)

        return enabled_media_kinds

    return {
        cggt.course.course_media.MEDIA_KIND_VIDEOS,
        cggt.course.course_media.MEDIA_KIND_DOCUMENTS,
        cggt.course.course_media.MEDIA_KIND_QUIZZES,
    }


def _run_video_export(
        player_client,
        course_document,
        site_host,
        contentable_id_by_content_id,
        output_directory_path):
    """Collect and download lesson videos when enabled."""

    jobs, lessons_without_video = cggt.course.course_media.collect_video_jobs(
        player_client,
        course_document,
        site_host,
        contentable_id_by_content_id,
        _report_operation,
        _open_resolve_progress)
    for lesson in lessons_without_video:
        try:
            reason = lesson["reason"]
        except KeyError:
            reason = "has no video"
        _report_operation(
            "lesson {content_id} {lesson_name} {reason}".format(
                content_id=lesson["content_id"],
                lesson_name=lesson["lesson_name"],
                reason=reason))
    videos_directory_path = os.path.join(
        output_directory_path,
        cggt.course.course_media.VIDEOS_DIRECTORY_NAME)
    cggt.course.course_media.write_wistia_catalog(
        videos_directory_path,
        jobs,
        _report_operation)
    total = len(jobs)
    video_number = 0
    for job in jobs:
        video_number = video_number + 1
        if cggt.course.course_media.is_content_directory_present(
                output_directory_path,
                cggt.course.course_media.MEDIA_KIND_VIDEOS,
                job["content_id"]):
            _report_operation(
                "skipping content ID {content_id}; destination already has files".format(
                    content_id=job["content_id"]))
            continue
        description = "{video_number}/{total} {lesson_name}".format(
            video_number=video_number,
            total=total,
            lesson_name=job["lesson_name"])
        progress = _ByteProgress(description)
        try:
            cggt.course.course_media.download_video_files(
                player_client,
                job,
                output_directory_path,
                progress,
                _report_operation)
        finally:
            progress.close()


def _run_document_export(
        player_client,
        course_document,
        site_host,
        contentable_id_by_content_id,
        output_directory_path):
    """Collect and download PDF documents when enabled."""

    jobs, skipped = cggt.course.course_media.collect_document_jobs(
        player_client,
        course_document,
        site_host,
        contentable_id_by_content_id,
        _report_operation)
    for row in skipped:
        _report_operation(
            "document {content_id} {name}: {reason}".format(
                content_id=row["content_id"],
                name=row["name"],
                reason=row["reason"]))
    for job in jobs:
        if cggt.course.course_media.is_content_directory_present(
                output_directory_path,
                cggt.course.course_media.MEDIA_KIND_DOCUMENTS,
                job["content_id"]):
            _report_operation(
                "skipping content ID {content_id}; destination already has files".format(
                    content_id=job["content_id"]))
            continue
        progress = _ByteProgress(job["name"])
        try:
            cggt.course.course_media.download_document_files(
                player_client,
                job,
                output_directory_path,
                progress,
                _report_operation)
        finally:
            progress.close()


def _run_quiz_export(
        player_client,
        course_document,
        site_host,
        contentable_id_by_content_id,
        output_directory_path):
    """Collect and write quiz JSON when enabled."""

    jobs, skipped = cggt.course.course_media.collect_quiz_jobs(
        player_client,
        course_document,
        site_host,
        contentable_id_by_content_id,
        _report_operation)
    for row in skipped:
        _report_operation(
            "quiz {content_id} {name}: {reason}".format(
                content_id=row["content_id"],
                name=row["name"],
                reason=row["reason"]))
    for job in jobs:
        if cggt.course.course_media.is_content_directory_present(
                output_directory_path,
                cggt.course.course_media.MEDIA_KIND_QUIZZES,
                job["content_id"]):
            _report_operation(
                "skipping content ID {content_id}; destination already has files".format(
                    content_id=job["content_id"]))
            continue
        cggt.course.course_media.download_quiz_files(
            player_client,
            job,
            output_directory_path,
            _report_operation)


def _report_operation(message):
    """Write one operation line to stderr."""

    sys.stderr.write(message)
    sys.stderr.write("\n")
    sys.stderr.flush()


def _load_json(filepath):
    """Read one JSON document from disk."""

    with open(filepath, "r", encoding="utf-8") as input_file:
        document = json.load(input_file)

    return document
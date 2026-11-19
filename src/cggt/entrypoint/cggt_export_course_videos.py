"""Download lesson M3U8 files and videos from a course export."""

import argparse
import json
import sys

import tqdm

import cggt.config.entrypoint.cggt_export_course_videos
import cggt.course.lesson_videos
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
        """Open one stderr bar for a single lesson video."""

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
    """Download lesson videos into content-ID directories and write the Wistia catalog."""

    # Three positionals: cookietruck session, course export, and the output directory.
    parser = argparse.ArgumentParser(
        prog=cggt.config.entrypoint.cggt_export_course_videos.PROG_NAME,
        description="Download lesson M3U8 files and videos from a cggt_export_course JSON file.")
    parser.add_argument(
        "session_filepath",
        help="Cookietruck JSON session file. The cookie_header field is sent as the Cookie header.")
    parser.add_argument(
        "course_export_filepath",
        help="JSON file written by cggt_export_course.")
    parser.add_argument(
        "output_directory_path",
        help="Directory for content-ID downloads and the wistia catalog.")
    parsed_arguments = parser.parse_args(argv)
    _report_operation("reading {filepath}".format(filepath=parsed_arguments.session_filepath))
    session_document = _load_json(parsed_arguments.session_filepath)
    _report_operation("reading {filepath}".format(filepath=parsed_arguments.course_export_filepath))
    course_document = _load_json(parsed_arguments.course_export_filepath)
    player_client = cggt.course.player_client.PlayerClient(session_document["cookie_header"])
    jobs, lessons_without_video = cggt.course.lesson_videos.collect_lesson_video_jobs(
        player_client,
        course_document,
        _report_operation,
        _open_resolve_progress)
    for lesson in lessons_without_video:
        _report_operation("lesson {content_id} {lesson_name} has no video".format(
            content_id=lesson["content_id"],
            lesson_name=lesson["lesson_name"]))
    cggt.course.lesson_videos.write_wistia_catalog(
        parsed_arguments.output_directory_path,
        jobs,
        _report_operation)
    total = len(jobs)
    video_number = 0
    for job in jobs:
        video_number = video_number + 1
        if cggt.course.lesson_videos.is_content_directory_present(
                parsed_arguments.output_directory_path,
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
            cggt.course.lesson_videos.download_lesson_files(
                player_client,
                job,
                parsed_arguments.output_directory_path,
                progress,
                _report_operation)
        finally:
            progress.close()

    return 0


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

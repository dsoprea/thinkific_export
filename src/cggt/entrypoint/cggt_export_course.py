"""Print one Thinkific course content hierarchy as JSON."""

import argparse
import json
import logging
import sys

import tqdm

import cggt.config.entrypoint.cggt_export_course
import cggt.config.thinkific
import cggt.course.catalog
import cggt.course.thinkific_client


_LOGGER = logging.getLogger(__name__)


class _ChapterExportProgress:
    """One stderr bar while each chapter's contents are loaded."""

    def __init__(self):
        """Defer opening the bar until the chapter count is known."""

        self._total = 0
        self._number = 0
        self._bar = None

    def begin(self, total):
        """Open a bar whose total is course plus chapter steps."""

        self._total = total
        self._bar = tqdm.tqdm(
            total=total,
            file=sys.stderr)

    def advance(self, label):
        """Move the bar one step and show its position and label."""

        self._number = self._number + 1
        description = "{number}/{total} {label}".format(
            number=self._number,
            total=self._total,
            label=label)
        self._bar.set_description(description)
        self._bar.update(1)

    def close(self):
        """Finish the bar."""

        if self._bar is not None:
            self._bar.close()


def main(argv=None):
    """Write the course, chapters, and chapter contents as JSON on stdout."""

    # Course ID is required and positional.
    parser = argparse.ArgumentParser(
        prog=cggt.config.entrypoint.cggt_export_course.PROG_NAME,
        description="Export one Thinkific course content hierarchy as JSON.")
    parser.add_argument(
        "course_id",
        type=int,
        help="Thinkific course ID to export.")
    parsed_arguments = parser.parse_args(argv)
    access_token, _signing_secret = cggt.config.thinkific.load_thinkific_credentials()
    thinkific_client = cggt.course.thinkific_client.ThinkificClient(access_token)
    chapter_progress = _ChapterExportProgress()
    document = cggt.course.catalog.load_course_content_document(
        thinkific_client,
        parsed_arguments.course_id,
        chapter_progress)
    encoded_document = json.dumps(document, indent=2, ensure_ascii=False)
    sys.stdout.write(encoded_document)
    sys.stdout.write("\n")

    return 0

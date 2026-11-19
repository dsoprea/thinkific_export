"""Print one Thinkific course content hierarchy as JSON."""

import argparse
import json
import logging
import sys

import cggt.config.entrypoint.cggt_export_course
import cggt.config.thinkific
import cggt.course.catalog
import cggt.course.thinkific_client


_LOGGER = logging.getLogger(__name__)


def main(argv=None):
    """Write the course, chapters, and chapter contents as JSON on stdout."""

    # Course ID is required and positional.
    parser = argparse.ArgumentParser(
        prog=cggt.config.entrypoint.cggt_export_course.PROG_NAME,
        description="Export one Thinkific course content hierarchy as JSON.")
    parser.add_argument("course_id", type=int)
    parsed_arguments = parser.parse_args(argv)
    access_token, _signing_secret = cggt.config.thinkific.load_thinkific_credentials()
    thinkific_client = cggt.course.thinkific_client.ThinkificClient(access_token)
    document = cggt.course.catalog.load_course_content_document(
        thinkific_client,
        parsed_arguments.course_id)
    encoded_document = json.dumps(document, indent=2, ensure_ascii=False)
    sys.stdout.write(encoded_document)
    sys.stdout.write("\n")

    return 0

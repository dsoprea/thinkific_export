"""Print Thinkific courses as a table."""

import argparse
import logging
import sys

import tabulate

import cggt.config.entrypoint.cggt_course_list
import cggt.config.thinkific
import cggt.course.catalog
import cggt.course.thinkific_client


_LOGGER = logging.getLogger(__name__)


def main(argv=None):
    """Load courses and write an ID, name, and created-at table to stderr."""

    # Parse first so ``-h`` does not require credentials.
    parser = argparse.ArgumentParser(
        prog=cggt.config.entrypoint.cggt_course_list.PROG_NAME,
        description="List Thinkific courses sorted by name.")
    parser.parse_args(argv)
    access_token, _signing_secret = cggt.config.thinkific.load_thinkific_credentials()
    thinkific_client = cggt.course.thinkific_client.ThinkificClient(access_token)
    rows = cggt.course.catalog.load_course_list_rows(thinkific_client)
    table_rows = []
    for row in rows:
        table_rows.append([row["id"], row["name"], row["created_at"]])
    table_plaintext = tabulate.tabulate(
        table_rows,
        headers=["ID", "Name", "Created At"],
        tablefmt="simple")
    sys.stderr.write(table_plaintext)
    sys.stderr.write("\n\n")

    return 0

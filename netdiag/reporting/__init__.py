"""Presentation: console output, HTML report and JSON export.
May depend on: config, utils, analysis. Must not import probes.

Public API of the package: other packages import from here, never from the files inside."""

from netdiag.reporting.html_report import (
    HTML_CSS,
    HTML_JS,
    build_report_html,
    hop_table_html,
    timeline_data,
    timeline_html,
    write_report,
)
from netdiag.reporting.json_export import write_json
from netdiag.reporting.console import print_console_summary, print_progress

__all__ = [
    "HTML_CSS",
    "timeline_data",
    "timeline_html",
    "HTML_JS",
    "hop_table_html",
    "build_report_html",
    "write_report",
    "write_json",
    "print_progress",
    "print_console_summary",
]

"""Step 1 of the pipeline: validate and clean a raw Circulation Item Inventories export.

Reads the pipe-delimited report downloaded from OCLC WMS, validates the header and
per-line field counts, drops discard statuses and unwanted item types, normalizes
cost values, strips stray double quotes, and blanks the LHR note fields (which can
contain patron, donor, and staff details). Writes:

    {LIBRARY}_inventory-evaluate.txt  -- cleaned input for the estimator scripts
    {LIBRARY}_inventory-errors.txt    -- malformed lines, only when any are found

Every dropped line is counted and reported by reason, so filtering is never silent.

Usage:
    python -m cve.prep_inventory ABC.Circulation_Item_Inventories.20260801.txt --library ABC
"""

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from cve.fields import (
    FIELD_COUNT,
    HEADER_LINE,
    IDX_COST,
    IDX_ITEM_TYPE,
    IDX_NONPUBLIC_NOTE,
    IDX_PUBLIC_NOTE,
    IDX_STATUS,
)

DEFAULT_EXCLUDED_STATUSES = frozenset(
    {"IN PROCESSING", "LOST", "MISSING", "WITHDRAWN", "CLAIMED RETURNED"}
)
DEFAULT_ITEM_TYPES = frozenset({"VOLUME"})

_COST_RE = re.compile(r"^\d+(\.\d+)?$")
_CURRENCY_RE = re.compile(r"(?i)usd|[$,\s]")
_PAREN_NOTE_RE = re.compile(r"\([^)]*\)")


class HeaderError(ValueError):
    """Raised when the input file's first line is not the expected 31-column header."""


@dataclass
class PrepConfig:
    item_types: frozenset | None = DEFAULT_ITEM_TYPES  # None disables the filter
    excluded_statuses: frozenset = DEFAULT_EXCLUDED_STATUSES
    keep_notes: bool = False


def validate_header(line):
    return line.strip() == HEADER_LINE


def normalize_cost(raw):
    """Normalize a cost value to a plain "X.XX" string.

    Real exports carry costs as "5.00", "$5.00", "5.00 USD", "USD 5.00",
    "1,234.00", or with a parenthetical note like "31.93 USD (for the set)".
    Returns (normalized, ok). An empty cost is normal: ("", True). A value
    that, after removing currency markers and parenthetical notes, still is
    not a plain non-negative number is blanked and flagged: ("", False).
    """
    cost = raw.strip()
    if not cost:
        return "", True
    cleaned = _CURRENCY_RE.sub("", _PAREN_NOTE_RE.sub("", cost))
    if _COST_RE.match(cleaned):
        return f"{float(cleaned):.2f}", True
    return "", False


def process_line(line, config):
    """Clean one raw data line.

    Returns (fields, drop_reason, cost_ok). fields is None when the line is
    dropped, with drop_reason saying why; cost_ok is False when a non-empty
    cost could not be parsed and was blanked (the row itself is kept).
    """
    field_count = line.count("|") + 1
    if field_count != FIELD_COUNT:
        return None, f"malformed line ({field_count} fields)", True

    fields = line.strip().split("|")

    status = fields[IDX_STATUS].strip().upper()
    if status in config.excluded_statuses:
        return None, f"status {status}", True

    if config.item_types is not None:
        item_type = fields[IDX_ITEM_TYPE].strip().upper()
        if item_type not in config.item_types:
            return None, f"item type {item_type}", True

    fields[IDX_COST], cost_ok = normalize_cost(fields[IDX_COST])

    if not config.keep_notes:
        fields[IDX_NONPUBLIC_NOTE] = ""
        fields[IDX_PUBLIC_NOTE] = ""

    fields = [field.replace('"', "").strip() for field in fields]
    return fields, None, cost_ok


def prep_file(input_path, output_path, error_path, config):
    """Run the full prep pass over input_path. Returns a summary dict."""
    drops = Counter()
    error_lines = []
    kept = 0
    line_count = 0
    unparseable_costs = 0

    with open(input_path, encoding="utf-8") as fh:
        first_line = fh.readline().strip()
        if not validate_header(first_line):
            raise HeaderError(first_line)

        with open(output_path, "w", encoding="utf-8") as out:
            out.write(first_line + "\n")
            for lineno, line in enumerate(fh, start=2):
                line_count += 1
                fields, reason, cost_ok = process_line(line, config)
                if fields is None:
                    drops[reason] += 1
                    if reason.startswith("malformed"):
                        error_lines.append(
                            f"Line {lineno}: {line.count('|') + 1} fields\n"
                            f"{line.strip()}\n{'-' * 60}\n"
                        )
                    continue
                if not cost_ok:
                    unparseable_costs += 1
                out.write("|".join(fields) + "\n")
                kept += 1

    if error_lines:
        with open(error_path, "w", encoding="utf-8") as ef:
            ef.writelines(error_lines)

    return {
        "processed": line_count,
        "kept": kept,
        "drops": drops,
        "errors": len(error_lines),
        "unparseable_costs": unparseable_costs,
        "output": str(output_path),
        "error_file": str(error_path),
    }


def check_field_counts(input_path, error_path):
    """Standalone field-count check of any pipe-delimited file (--check-only mode).

    Returns (line_count, error_count). Replaces the old check-field-count.py.
    """
    line_count = 0
    error_lines = []
    with open(input_path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line_count += 1
            field_count = line.count("|") + 1
            if field_count != FIELD_COUNT:
                error_lines.append(
                    f"Line {lineno}: {field_count} fields\n{line.strip()}\n{'-' * 60}\n"
                )

    if error_lines:
        with open(error_path, "w", encoding="utf-8") as ef:
            ef.writelines(error_lines)
        print(f"\nWARNING: {len(error_lines)} malformed lines written to: {error_path}")
    else:
        print("\nOK: no malformed lines found.")
    print(f"Complete - {line_count} lines processed (header included).")
    return line_count, len(error_lines)


def print_summary(summary):
    print(f"\nSaved {summary['kept']:,} records to: {summary['output']}")
    print(f"Processed {summary['processed']:,} data lines.")
    if summary["unparseable_costs"]:
        print(
            f"WARNING: {summary['unparseable_costs']:,} unparseable cost values "
            "were blanked (rows kept)."
        )
    if summary["drops"]:
        total_dropped = sum(summary["drops"].values())
        print(f"\nDropped {total_dropped:,} lines:")
        for reason, count in summary["drops"].most_common():
            print(f"  {reason}: {count:,}")
        print(
            "Review this list. If your library shelves collections under item types\n"
            "other than VOLUME, re-run with --item-types (e.g. --item-types "
            "VOLUME,CIRC_MANAGED)\nor --no-item-type-filter to include them."
        )
    else:
        print("\nNo lines dropped.")
    if summary["errors"]:
        print(
            f"\nWARNING: {summary['errors']:,} malformed lines written to: "
            f"{summary['error_file']}"
        )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m cve.prep_inventory",
        description="Validate and clean a WMS Circulation Item Inventories export.",
    )
    parser.add_argument("input_file", help="Raw pipe-delimited inventory export")
    parser.add_argument(
        "--library",
        required=True,
        help="Library code used to name the output files (e.g. ABC)",
    )
    parser.add_argument(
        "--item-types",
        default=",".join(sorted(DEFAULT_ITEM_TYPES)),
        help="Comma-separated Item_Type values to keep, case-insensitive (default: VOLUME)",
    )
    parser.add_argument(
        "--no-item-type-filter",
        action="store_true",
        help="Keep every Item_Type",
    )
    parser.add_argument(
        "--exclude-statuses",
        default=",".join(sorted(DEFAULT_EXCLUDED_STATUSES)),
        help="Comma-separated Item_Status_Current_Status values to drop",
    )
    parser.add_argument(
        "--keep-notes",
        action="store_true",
        help=(
            "Keep the LHR note fields. They are blanked by default because they can "
            "contain patron, donor, and staff details."
        ),
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only report field-count problems in INPUT_FILE, then exit",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for output files (default: current directory)",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    error_path = out_dir / f"{args.library}_inventory-errors.txt"

    if args.check_only:
        _, errors = check_field_counts(args.input_file, error_path)
        return {"errors": errors}

    config = PrepConfig(
        item_types=(
            None
            if args.no_item_type_filter
            else frozenset(t.strip().upper() for t in args.item_types.split(",") if t.strip())
        ),
        excluded_statuses=frozenset(
            s.strip().upper() for s in args.exclude_statuses.split(",") if s.strip()
        ),
        keep_notes=args.keep_notes,
    )
    output_path = out_dir / f"{args.library}_inventory-evaluate.txt"

    try:
        summary = prep_file(args.input_file, output_path, error_path, config)
    except HeaderError as exc:
        print("ERROR: file is missing the expected header or columns are out of order.")
        print(f"First line detected:\n{exc}")
        sys.exit(1)

    print_summary(summary)
    return summary


if __name__ == "__main__":
    main()

from pathlib import Path

import pytest

from cve.fields import (
    EXPECTED_HEADER,
    FIELD_COUNT,
    HEADER_LINE,
    IDX_NONPUBLIC_NOTE,
    IDX_PUBLIC_NOTE,
)
from cve.prep_inventory import (
    HeaderError,
    PrepConfig,
    main,
    normalize_cost,
    prep_file,
    validate_header,
)

FIXTURE = Path(__file__).parent / "data" / "sample_inventory.txt"

# Fixture contents: 15 data rows — 8 keepable VOLUME rows, 5 excluded statuses,
# 1 CIRC_MANAGED row, 1 malformed (30-field) row.
KEPT_DEFAULT = 8


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$24.99", ("24.99", True)),
        ("1,234.00", ("1234.00", True)),
        ("24.99", ("24.99", True)),
        ("  $5 ", ("5.00", True)),
        ("7.24 USD", ("7.24", True)),
        ("USD 5.00", ("5.00", True)),
        ("31.93 USD (for the set)", ("31.93", True)),
        ("0", ("0.00", True)),
        ("", ("", True)),
        ("   ", ("", True)),
        ("12.34.56", ("", False)),
        ("-5.00", ("", False)),
        ("FREE", ("", False)),
    ],
)
def test_normalize_cost(raw, expected):
    assert normalize_cost(raw) == expected


def test_validate_header_accepts_expected():
    assert validate_header(HEADER_LINE)
    assert validate_header(HEADER_LINE + "\n")


def test_validate_header_rejects_reordered_or_short():
    reordered = "|".join(reversed(EXPECTED_HEADER))
    assert not validate_header(reordered)
    assert not validate_header("|".join(EXPECTED_HEADER[:-1]))
    assert not validate_header("")


def run_main(tmp_path, *extra):
    return main([str(FIXTURE), "--library", "ABC", "--output-dir", str(tmp_path), *extra])


def test_main_default_run(tmp_path):
    summary = run_main(tmp_path)

    out = tmp_path / "ABC_inventory-evaluate.txt"
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == HEADER_LINE
    assert summary["kept"] == KEPT_DEFAULT
    assert len(lines) - 1 == KEPT_DEFAULT

    for line in lines[1:]:
        fields = line.split("|")
        assert len(fields) == FIELD_COUNT
        assert '"' not in line
        # note fields are blanked by default (privacy)
        assert fields[IDX_NONPUBLIC_NOTE] == ""
        assert fields[IDX_PUBLIC_NOTE] == ""

    # drops are counted per reason, never silent
    drops = summary["drops"]
    assert drops["item type CIRC_MANAGED"] == 1
    assert drops["malformed line (30 fields)"] == 1
    status_drops = {r: c for r, c in drops.items() if r.startswith("status ")}
    assert sum(status_drops.values()) == 5
    assert "status LOST" in status_drops

    # the unparseable "12.34.56" cost was blanked but the row kept
    assert summary["unparseable_costs"] == 1

    errors = (tmp_path / "ABC_inventory-errors.txt").read_text(encoding="utf-8")
    assert "30 fields" in errors
    assert "Truncated Row" in errors


def test_quotes_stripped(tmp_path):
    run_main(tmp_path)
    text = (tmp_path / "ABC_inventory-evaluate.txt").read_text(encoding="utf-8")
    assert "The Unfinished Story" in text
    assert '"' not in text


def test_keep_notes(tmp_path):
    run_main(tmp_path, "--keep-notes")
    text = (tmp_path / "ABC_inventory-evaluate.txt").read_text(encoding="utf-8")
    assert "Gift of Jane Donor" in text
    assert "paid by .p0000000" in text


def test_item_type_opt_in(tmp_path):
    summary = run_main(tmp_path, "--item-types", "VOLUME,CIRC_MANAGED")
    assert summary["kept"] == KEPT_DEFAULT + 1
    text = (tmp_path / "ABC_inventory-evaluate.txt").read_text(encoding="utf-8")
    assert "Special Collections Item" in text


def test_no_item_type_filter(tmp_path):
    summary = run_main(tmp_path, "--no-item-type-filter")
    assert summary["kept"] == KEPT_DEFAULT + 1
    assert not any(r.startswith("item type") for r in summary["drops"])


def test_check_only(tmp_path):
    result = run_main(tmp_path, "--check-only")
    assert result["errors"] == 1
    errors = (tmp_path / "ABC_inventory-errors.txt").read_text(encoding="utf-8")
    assert "30 fields" in errors
    # check-only must not produce a cleaned file
    assert not (tmp_path / "ABC_inventory-evaluate.txt").exists()


def test_bad_header_exits(tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("Wrong|Header|Line\nfoo|bar|baz\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        main([str(bad), "--library", "ABC", "--output-dir", str(tmp_path)])


def test_prep_file_raises_header_error(tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("Wrong|Header|Line\n", encoding="utf-8")
    with pytest.raises(HeaderError):
        prep_file(bad, tmp_path / "out.txt", tmp_path / "err.txt", PrepConfig())

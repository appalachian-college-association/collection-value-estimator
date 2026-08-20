from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cve.generate_item_estimates import build_estimates, extract_decade
from cve.generate_item_estimates import main as estimates_main
from cve.prep_inventory import main as prep_main

FIXTURE = Path(__file__).parent / "data" / "sample_inventory.txt"


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (1987, 1980),
        ("1987", 1980),
        (1990.0, 1990),
        (2000, 2000),
    ],
)
def test_extract_decade(year, expected):
    assert extract_decade(year) == expected


@pytest.mark.parametrize("year", [850, "0850", None, "garbage", "", np.nan])
def test_extract_decade_unusable(year):
    assert np.isnan(extract_decade(year))


def test_build_estimates_sources():
    df = pd.DataFrame(
        {
            "OCLC_Number": ["1", "2", "3"],
            "Title": ["Real Cost", "Decade Estimate", "Global Estimate"],
            "Author_Name": ["A", "B", "C"],
            "Publication_Date": ["1987", "1985", ""],
            "Item_Barcode": ["b1", "b2", "b3"],
            "LHR_Item_Cost": ["10.00", "", ""],
        },
        dtype=str,
    )
    result = build_estimates(df)

    assert list(result.columns) == [
        "OCLC_Number",
        "Title",
        "Author_Name",
        "Publication_Date",
        "Item_Barcode",
        "LHR_Item_Cost",
        "Final_Cost",
        "Cost_Source",
    ]
    assert result["Final_Cost"].tolist() == ["10.00", "10.00", "10.00"]
    assert result["Cost_Source"].tolist() == [
        "Real",
        "Estimated: 1980s",
        "Estimated: Global Average",
    ]
    assert result["Publication_Date"].tolist() == ["1987", "1985", ""]


def test_main_end_to_end(tmp_path):
    prep_main([str(FIXTURE), "--library", "ABC", "--output-dir", str(tmp_path)])
    evaluate_file = tmp_path / "ABC_inventory-evaluate.txt"

    estimates_main([str(evaluate_file), "--library", "ABC", "--output-dir", str(tmp_path)])

    output = tmp_path / "ABC_item_estimates.csv"
    result = pd.read_csv(output, dtype=str)
    assert len(result) == 8  # the 8 kept rows from the fixture
    # every item ends up with a final cost (global average covers the rest)
    assert result["Final_Cost"].notna().all()
    # rows whose cost was blank or unparseable are marked as estimates
    assert (result["Cost_Source"] != "Real").sum() == 3

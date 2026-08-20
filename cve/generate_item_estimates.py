"""Per-item cost estimates: export a CSV assigning every item a real or estimated cost.

Reads the cleaned file produced by cve.prep_inventory. Items with a real cost keep
it; items without one get the average cost of items from the same publication
decade, falling back to the collection-wide average when the decade has no cost
data (or the publication date is missing).

Usage:
    python -m cve.generate_item_estimates ABC_inventory-evaluate.txt --library ABC
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DELIMITER = "|"

EXPORT_COLUMNS = [
    "OCLC_Number",
    "Title",
    "Author_Name",
    "Publication_Date",
    "Item_Barcode",
    "LHR_Item_Cost",
    "Final_Cost",
    "Cost_Source",
]

MIN_PLAUSIBLE_YEAR = 1000


def extract_decade(year):
    """Return the publication decade (e.g. 1987 -> 1980), or NaN if unusable."""
    try:
        year = int(year)
    except (TypeError, ValueError):
        return np.nan
    if year >= MIN_PLAUSIBLE_YEAR:
        return (year // 10) * 10
    return np.nan


def build_estimates(df):
    """Assign Final_Cost and Cost_Source to every row; return the export DataFrame."""
    df = df.copy()

    df["LHR_Item_Cost"] = pd.to_numeric(df["LHR_Item_Cost"], errors="coerce")
    df["Publication_Date"] = pd.to_numeric(df["Publication_Date"], errors="coerce")

    # Remove stray double quotes and whitespace from the remaining string fields
    for col in df.select_dtypes(include="object"):
        df[col] = df[col].str.replace('"', "", regex=False).str.strip()

    df["Decade"] = df["Publication_Date"].apply(extract_decade)

    avg_cost_by_decade = (
        df.dropna(subset=["LHR_Item_Cost", "Decade"]).groupby("Decade")["LHR_Item_Cost"].mean()
    )
    global_avg = df["LHR_Item_Cost"].mean()

    def estimate_cost(row):
        if not pd.isna(row["LHR_Item_Cost"]):
            return row["LHR_Item_Cost"], "Real"
        if row["Decade"] in avg_cost_by_decade.index:
            return avg_cost_by_decade[row["Decade"]], f"Estimated: {int(row['Decade'])}s"
        return global_avg, "Estimated: Global Average"

    df[["Final_Cost", "Cost_Source"]] = df.apply(estimate_cost, axis=1, result_type="expand")

    df["Final_Cost"] = df["Final_Cost"].apply(lambda x: f"{x:.2f}" if not pd.isna(x) else "")
    df["Publication_Date"] = df["Publication_Date"].apply(
        lambda x: str(int(x)) if not pd.isna(x) else ""
    )

    return df[EXPORT_COLUMNS]


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m cve.generate_item_estimates",
        description="Export per-item cost estimates from a prepped inventory file.",
    )
    parser.add_argument("input_file", help="Cleaned file from cve.prep_inventory")
    parser.add_argument(
        "--library",
        required=True,
        help="Library code used to name the output file (e.g. ABC)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for the output CSV (default: current directory)",
    )
    args = parser.parse_args(argv)

    df = pd.read_csv(args.input_file, delimiter=DELIMITER, dtype=str)
    df_export = build_estimates(df)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_file = out_dir / f"{args.library}_item_estimates.csv"
    df_export.to_csv(output_file, index=False)

    print(f"Exported {len(df_export)} item-level cost estimates to {output_file}")
    return df_export


if __name__ == "__main__":
    main()

"""Step 2 of the pipeline: analyze a prepped inventory file and estimate collection value.

Reads the cleaned file produced by cve.prep_inventory, prints a structural and
cost analysis to the console, estimates total collection value (stratified by
publication decade and shelving location, plus a simple-average comparison),
saves charts, and writes a summary report:

    {LIBRARY}_valuation_report.txt
    {LIBRARY}_evaluator-charts.png

Usage:
    python -m cve.estimator ABC_inventory-evaluate.txt --library ABC
"""

import argparse
import sys
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


def _pct(part, whole):
    """Percentage that tolerates an empty collection."""
    return part / whole * 100 if whole else 0.0


class LibraryCollectionAnalyzer:
    def __init__(self, file_path, delimiter="|"):
        """
        Initialize the analyzer with a cleaned inventory file.

        Args:
            file_path (str): Path to the pipe-delimited file from cve.prep_inventory
            delimiter (str): Delimiter used in the file (default: '|')
        """
        self.file_path = file_path
        self.delimiter = delimiter
        self.df = None
        self.df_with_costs = None
        self.load_data()

    def load_data(self):
        """Load and clean the library data."""
        self.df = pd.read_csv(self.file_path, delimiter=self.delimiter, dtype=str)

        # Clean column names (remove any whitespace)
        self.df.columns = self.df.columns.str.strip()

        # Convert cost column to numeric, handling empty/null values
        self.df["LHR_Item_Cost_Numeric"] = pd.to_numeric(
            self.df["LHR_Item_Cost"]
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False),
            errors="coerce",
        )

        # Convert publication date to numeric
        self.df["Publication_Year"] = pd.to_numeric(self.df["Publication_Date"], errors="coerce")

        # Create decade grouping
        self.df["Publication_Decade"] = (self.df["Publication_Year"] // 10) * 10

        # Create records with cost data
        self.df_with_costs = self.df[self.df["LHR_Item_Cost_Numeric"].notna()].copy()

        print("Data loaded successfully!")
        print(f"Total records: {len(self.df):,}")
        print(f"Records with cost data: {len(self.df_with_costs):,}")
        print(f"Percentage with costs: {_pct(len(self.df_with_costs), len(self.df)):.1f}%")

    def analyze_collection_structure(self):
        """Analyze the structure of the collection."""
        print("\n" + "=" * 60)
        print("COLLECTION STRUCTURE ANALYSIS")
        print("=" * 60)

        # Basic statistics
        print("\nBASIC STATISTICS:")
        print(f"Total items: {len(self.df):,}")
        print(f"Items with cost data: {len(self.df_with_costs):,}")
        print(f"Coverage: {_pct(len(self.df_with_costs), len(self.df)):.1f}%")

        # Publication date range
        pub_years = self.df["Publication_Year"].dropna()
        if len(pub_years) > 0:
            print("\nPUBLICATION DATES:")
            print(f"Earliest: {int(pub_years.min())}")
            print(f"Latest: {int(pub_years.max())}")
            print(f"Median: {int(pub_years.median())}")

        # Location distribution
        print("\nTOP 10 LOCATIONS:")
        location_counts = self.df["Item_Permanent_Shelving_Location"].value_counts()
        for location, count in location_counts.head(10).items():
            print(f"  {location}: {count:,} ({_pct(count, len(self.df)):.1f}%)")

        # Material format
        print("\nMATERIAL FORMATS:")
        format_counts = self.df["Material_Format"].value_counts()
        for fmt, count in format_counts.items():
            print(f"  {fmt}: {count:,} ({_pct(count, len(self.df)):.1f}%)")

        # Decade distribution
        print("\nBY DECADE:")
        decade_counts = self.df["Publication_Decade"].value_counts().sort_index()
        for decade, count in decade_counts.items():
            if pd.notna(decade):
                print(f"  {int(decade)}s: {count:,} ({_pct(count, len(self.df)):.1f}%)")

    def analyze_cost_data(self):
        """Analyze the available cost data."""
        if len(self.df_with_costs) == 0:
            print("\nNo cost data available for analysis!")
            return

        print("\n" + "=" * 60)
        print("COST DATA ANALYSIS")
        print("=" * 60)

        costs = self.df_with_costs["LHR_Item_Cost_Numeric"]

        print("\nCOST STATISTICS:")
        print(f"Mean cost: ${costs.mean():.2f}")
        print(f"Median cost: ${costs.median():.2f}")
        print(f"Standard deviation: ${costs.std():.2f}")
        print(f"Minimum: ${costs.min():.2f}")
        print(f"Maximum: ${costs.max():.2f}")

        # Cost by decade
        print("\nAVERAGE COST BY DECADE:")
        decade_costs = self.df_with_costs.groupby("Publication_Decade")[
            "LHR_Item_Cost_Numeric"
        ].agg(["mean", "count", "std"])
        for decade, row in decade_costs.iterrows():
            if pd.notna(decade) and row["count"] > 0:
                print(
                    f"  {int(decade)}s: ${row['mean']:.2f} "
                    f"(n={int(row['count'])}, std=${row['std']:.2f})"
                )

        # Cost by location
        print("\nAVERAGE COST BY LOCATION:")
        location_costs = self.df_with_costs.groupby("Item_Permanent_Shelving_Location")[
            "LHR_Item_Cost_Numeric"
        ].agg(["mean", "count", "std"])
        for location, row in location_costs.iterrows():
            if row["count"] > 0:
                print(
                    f"  {location}: ${row['mean']:.2f} "
                    f"(n={int(row['count'])}, std=${row['std']:.2f})"
                )

    def estimate_collection_value(self, confidence_level=0.95):
        """
        Estimate the total collection value using stratified sampling.

        Args:
            confidence_level (float): Confidence level for intervals (default: 0.95)

        Returns:
            dict with stratified_estimate, confidence_interval, simple_estimate,
            and per-stratum details — or None when there is no cost data.
        """
        if len(self.df_with_costs) == 0:
            print("\nCannot estimate value without cost data!")
            return None

        print("\n" + "=" * 60)
        print("COLLECTION VALUE ESTIMATION")
        print("=" * 60)

        total_estimate = 0
        total_variance = 0
        estimation_details = []

        # Strategy 1: Estimate by decade and shelving location
        print("\nSTRATIFIED ESTIMATION (by decade and shelving location):")

        for decade in self.df["Publication_Decade"].dropna().unique():
            for location in self.df["Item_Permanent_Shelving_Location"].unique():
                # Get subset for this stratum
                stratum_all = self.df[
                    (self.df["Publication_Decade"] == decade)
                    & (self.df["Item_Permanent_Shelving_Location"] == location)
                ]
                stratum_with_costs = self.df_with_costs[
                    (self.df_with_costs["Publication_Decade"] == decade)
                    & (self.df_with_costs["Item_Permanent_Shelving_Location"] == location)
                ]

                if len(stratum_all) > 0 and len(stratum_with_costs) > 0:
                    # Calculate statistics for this stratum
                    n_total = len(stratum_all)
                    n_sample = len(stratum_with_costs)
                    mean_cost = stratum_with_costs["LHR_Item_Cost_Numeric"].mean()
                    std_cost = stratum_with_costs["LHR_Item_Cost_Numeric"].std()

                    # Estimate for this stratum
                    stratum_estimate = n_total * mean_cost
                    stratum_variance = (
                        (n_total**2) * (std_cost**2) / n_sample if not pd.isna(std_cost) else 0
                    )

                    total_estimate += stratum_estimate
                    total_variance += stratum_variance

                    estimation_details.append(
                        {
                            "decade": int(decade),
                            "location": location,
                            "total_items": n_total,
                            "sample_items": n_sample,
                            "mean_cost": mean_cost,
                            "std_cost": std_cost if not pd.isna(std_cost) else 0,
                            "stratum_estimate": stratum_estimate,
                        }
                    )

                    print(
                        f"  {int(decade)}s - {location}: {n_total:,} items, "
                        f"sample: {n_sample}, avg: ${mean_cost:.2f}, "
                        f"estimate: ${stratum_estimate:,.0f}"
                    )

        # Calculate confidence intervals
        std_error = np.sqrt(total_variance)
        z_score = stats.norm.ppf((1 + confidence_level) / 2)
        margin_error = z_score * std_error

        print("\nFINAL ESTIMATES:")
        print(f"Total estimated value: ${total_estimate:,.0f}")
        print(f"Standard error: ${std_error:,.0f}")
        print(
            f"{confidence_level * 100:.0f}% Confidence interval: "
            f"${total_estimate - margin_error:,.0f} - ${total_estimate + margin_error:,.0f}"
        )

        # Simple average method for comparison
        simple_avg = self.df_with_costs["LHR_Item_Cost_Numeric"].mean()
        simple_estimate = len(self.df) * simple_avg
        print("\nFor comparison:")
        print(f"Simple average method: ${simple_estimate:,.0f}")
        print(f"  (Overall average: ${simple_avg:.2f} x {len(self.df):,} items)")

        return {
            "stratified_estimate": total_estimate,
            "confidence_interval": (total_estimate - margin_error, total_estimate + margin_error),
            "simple_estimate": simple_estimate,
            "details": estimation_details,
        }

    def create_visualizations(self, output_path=None, show=False):
        """Create visualizations of the cost data.

        Args:
            output_path (str): PNG path to save the charts to (skipped if None)
            show (bool): Display the charts in a window (blocks until closed)
        """
        if len(self.df_with_costs) == 0:
            print("\nNo cost data available for visualization!")
            return

        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle("Library Collection Cost Analysis", fontsize=16)

        # Cost distribution
        axes[0, 0].hist(
            self.df_with_costs["LHR_Item_Cost_Numeric"], bins=30, edgecolor="black", alpha=0.7
        )
        axes[0, 0].set_title("Distribution of Item Costs")
        axes[0, 0].set_xlabel("Cost ($)")
        axes[0, 0].set_ylabel("Frequency")

        # Cost by decade
        decade_costs = self.df_with_costs.groupby("Publication_Decade")[
            "LHR_Item_Cost_Numeric"
        ].mean()
        decade_costs.plot(kind="bar", ax=axes[0, 1])
        axes[0, 1].set_title("Average Cost by Publication Decade")
        axes[0, 1].set_xlabel("Decade")
        axes[0, 1].set_ylabel("Average Cost ($)")
        axes[0, 1].tick_params(axis="x", rotation=45)

        # Collection size by decade
        decade_counts = self.df["Publication_Decade"].value_counts().sort_index()
        decade_counts.plot(kind="bar", ax=axes[1, 0])
        axes[1, 0].set_title("Collection Size by Publication Decade")
        axes[1, 0].set_xlabel("Decade")
        axes[1, 0].set_ylabel("Number of Items")
        axes[1, 0].tick_params(axis="x", rotation=45)

        # Cost coverage by decade
        coverage_by_decade = (
            self.df_with_costs.groupby("Publication_Decade").size()
            / self.df.groupby("Publication_Decade").size()
            * 100
        )
        coverage_by_decade.plot(kind="bar", ax=axes[1, 1])
        axes[1, 1].set_title("Cost Data Coverage by Decade (%)")
        axes[1, 1].set_xlabel("Decade")
        axes[1, 1].set_ylabel("Coverage (%)")
        axes[1, 1].tick_params(axis="x", rotation=45)

        plt.tight_layout()
        if output_path:
            plt.savefig(output_path)
            print(f"\nCharts saved to: {output_path}")
        if show:
            plt.show()
        plt.close(fig)

    def export_summary_report(self, results, output_file):
        """Export a summary report to a text file.

        Args:
            results: the dict returned by estimate_collection_value() (or None)
            output_file (str): path of the report to write
        """
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("LIBRARY COLLECTION VALUATION REPORT\n")
            f.write("=" * 50 + "\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("Collection Summary:\n")
            f.write(f"  Total items: {len(self.df):,}\n")
            f.write(f"  Items with cost data: {len(self.df_with_costs):,}\n")
            f.write(
                f"  Cost data coverage: {_pct(len(self.df_with_costs), len(self.df)):.1f}%\n\n"
            )

            if results:
                f.write("Valuation Results:\n")
                f.write(f"  Stratified estimate: ${results['stratified_estimate']:,.0f}\n")
                f.write(
                    f"  95% Confidence interval: ${results['confidence_interval'][0]:,.0f} "
                    f"- ${results['confidence_interval'][1]:,.0f}\n"
                )
                f.write(f"  Simple average estimate: ${results['simple_estimate']:,.0f}\n")

        print(f"\nSummary report exported to: {output_file}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m cve.estimator",
        description="Estimate total collection value from a prepped inventory file.",
    )
    parser.add_argument("input_file", help="Cleaned file from cve.prep_inventory")
    parser.add_argument(
        "--library",
        required=True,
        help="Library code used to name the output files (e.g. ABC)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display charts in a window (blocks until the window is closed)",
    )
    parser.add_argument("--no-charts", action="store_true", help="Skip chart generation")
    args = parser.parse_args(argv)

    try:
        analyzer = LibraryCollectionAnalyzer(args.input_file)
    except FileNotFoundError:
        print(f"\nFile not found: {args.input_file}")
        print("Run cve.prep_inventory first, or check the path.")
        sys.exit(1)

    analyzer.analyze_collection_structure()
    analyzer.analyze_cost_data()
    results = analyzer.estimate_collection_value()

    if not args.no_charts:
        analyzer.create_visualizations(f"{args.library}_evaluator-charts.png", show=args.show)

    analyzer.export_summary_report(results, f"{args.library}_valuation_report.txt")
    return analyzer, results


if __name__ == "__main__":
    main()

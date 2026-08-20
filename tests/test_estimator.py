from pathlib import Path

import pytest

from cve.estimator import LibraryCollectionAnalyzer
from cve.fields import HEADER_LINE
from cve.prep_inventory import main as prep_main

FIXTURE = Path(__file__).parent / "data" / "sample_inventory.txt"

# Hand-computed expectations for the fixture's 8 kept rows (all location STACKS).
# Costs by decade: 1980s -> 24.99, 20.00 (plus 2 costless rows, 4 items total);
# 1990s -> 1234.00 (1 item); 2000s -> 10.00 (1 item); 850s -> 5.00 (1 item);
# 1 row with no publication date (excluded from stratified estimate).
#   Stratified: 4 * mean(24.99, 20.00) + 1234.00 + 10.00 + 5.00 = 1338.98
#   Simple: mean(24.99, 1234.00, 10.00, 5.00, 20.00) * 8 items = 2070.384
EXPECTED_STRATIFIED = 1338.98
EXPECTED_SIMPLE = 2070.384


@pytest.fixture
def evaluate_file(tmp_path):
    prep_main([str(FIXTURE), "--library", "ABC", "--output-dir", str(tmp_path)])
    return tmp_path / "ABC_inventory-evaluate.txt"


def test_estimates_match_hand_computed(evaluate_file):
    analyzer = LibraryCollectionAnalyzer(str(evaluate_file))
    results = analyzer.estimate_collection_value()

    assert results["stratified_estimate"] == pytest.approx(EXPECTED_STRATIFIED)
    assert results["simple_estimate"] == pytest.approx(EXPECTED_SIMPLE)
    low, high = results["confidence_interval"]
    assert low <= results["stratified_estimate"] <= high
    assert len(results["details"]) == 4  # one stratum per decade with cost data


def test_analysis_methods_run(evaluate_file, capsys):
    analyzer = LibraryCollectionAnalyzer(str(evaluate_file))
    analyzer.analyze_collection_structure()
    analyzer.analyze_cost_data()
    out = capsys.readouterr().out
    assert "COLLECTION STRUCTURE ANALYSIS" in out
    assert "COST DATA ANALYSIS" in out


def test_export_uses_results_without_recomputing(evaluate_file, tmp_path, capsys):
    analyzer = LibraryCollectionAnalyzer(str(evaluate_file))
    results = analyzer.estimate_collection_value()
    capsys.readouterr()  # discard output so far

    report = tmp_path / "ABC_valuation_report.txt"
    analyzer.export_summary_report(results, str(report))

    printed = capsys.readouterr().out
    assert "STRATIFIED ESTIMATION" not in printed  # no recomputation output

    text = report.read_text(encoding="utf-8")
    assert "Total items: 8" in text
    assert "Stratified estimate: $1,339" in text
    assert "Simple average estimate: $2,070" in text


def test_charts_saved(evaluate_file, tmp_path):
    analyzer = LibraryCollectionAnalyzer(str(evaluate_file))
    chart_path = tmp_path / "ABC_evaluator-charts.png"
    analyzer.create_visualizations(str(chart_path), show=False)
    assert chart_path.exists()
    assert chart_path.stat().st_size > 0


def test_no_cost_data_is_handled(tmp_path):
    # A file whose rows have no costs at all: estimate returns None, export still works
    no_cost = tmp_path / "no-cost.txt"
    fields = [""] * 31
    fields[0], fields[2], fields[4], fields[13] = "ABC", "STACKS", "VOLUME", "1990"
    no_cost.write_text(HEADER_LINE + "\n" + "|".join(fields) + "\n", encoding="utf-8")

    analyzer = LibraryCollectionAnalyzer(str(no_cost))
    results = analyzer.estimate_collection_value()
    assert results is None

    report = tmp_path / "report.txt"
    analyzer.export_summary_report(results, str(report))
    text = report.read_text(encoding="utf-8")
    assert "Total items: 1" in text
    assert "Valuation Results" not in text


def test_empty_file_no_division_error(tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text(HEADER_LINE + "\n", encoding="utf-8")
    analyzer = LibraryCollectionAnalyzer(str(empty))
    assert len(analyzer.df) == 0
    assert analyzer.estimate_collection_value() is None

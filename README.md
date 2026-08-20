# Library Collection Value Estimator

Estimates the replacement value of a library collection from item-level data
exported from OCLC WorldShare Management Services (WMS). Built for Appalachian
College Association member libraries. It uses the item cost data your library
already has to produce a statistically grounded estimate — stratified by
publication decade and shelving location, with a 95% confidence interval —
plus a simple-average estimate for comparison, charts, and an optional
per-item cost spreadsheet.

## Pipeline

```
{LIB}.Circulation_Item_Inventories.{date}.txt      (raw WMS export)
        |
        v
python -m cve.prep_inventory RAW.txt --library LIB
        |
        +--> LIB_inventory-evaluate.txt            (cleaned data)
        +--> LIB_inventory-errors.txt              (malformed lines, if any)
        |
        v
python -m cve.estimator LIB_inventory-evaluate.txt --library LIB
        |
        +--> LIB_valuation_report.txt              (summary valuation report)
        +--> LIB_evaluator-charts.png              (charts)

python -m cve.generate_item_estimates LIB_inventory-evaluate.txt --library LIB
        |
        +--> LIB_item_estimates.csv                (per-item cost estimates)
```

All output filenames are prefixed with your library code, so runs for
different libraries never overwrite each other.

## Step 0: Get your input file

You need the **Circulation Item Inventories** report from OCLC WMS — a
pipe-delimited text file with 31 columns (the exact expected header is defined
in [`cve/fields.py`](cve/fields.py)).

The recommended way to download it is ACA's
[wms-circ-tools](https://github.com/appalachian-college-association/wms-circ-tools)
`data_fetcher.py`, which pulls reports from the OCLC SFTP server. Your OCLC
credentials live only in that tool's local `.env` file — this project never
touches credentials. Any other export path works too, as long as the file has
the expected 31-column header.

## Install

Requires Python 3.10+.

```powershell
git clone git@github.com:appalachian-college-association/collection-value-estimator.git
cd collection-value-estimator
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

(Developers: `pip install -e .[dev]` also installs pytest and ruff.)

## Usage

Using a generic library code `ABC` as the example:

```powershell
# 1. Clean and validate the raw export
python -m cve.prep_inventory ABC.Circulation_Item_Inventories.20260801.txt --library ABC

# 2. Run the valuation
python -m cve.estimator ABC_inventory-evaluate.txt --library ABC

# 3. (Optional) per-item cost estimates for reconciliation/insurance detail
python -m cve.generate_item_estimates ABC_inventory-evaluate.txt --library ABC
```

Results print to the console; the report is saved as `ABC_valuation_report.txt`.
Charts are saved as `ABC_evaluator-charts.png` (pass `--show` to also open
them in a window, or `--no-charts` to skip them).

### Read the drop summary — it matters

`prep_inventory` prints a count of every line it dropped, grouped by reason.
**Review it every time.** For example:

```
Dropped 1,234 lines:
  item type CIRC_MANAGED: 1,180
  status LOST: 42
  status WITHDRAWN: 12
```

By default only items with `Item_Type` = `VOLUME` are kept. Libraries differ:
if your library shelves collections (special collections, media, etc.) under
other item types, those items are **excluded from the valuation** unless you
opt them in:

```powershell
python -m cve.prep_inventory RAW.txt --library ABC --item-types VOLUME,CIRC_MANAGED
# or keep every item type:
python -m cve.prep_inventory RAW.txt --library ABC --no-item-type-filter
```

Items with status `IN PROCESSING`, `LOST`, `MISSING`, `WITHDRAWN`, or
`CLAIMED RETURNED` are excluded by default (override with `--exclude-statuses`).

### Other prep options

- `--keep-notes` — the `LHR_Item_Nonpublic_Note` and `LHR_Item_Public_Note`
  fields are **blanked by default** because they can contain patron, donor, and
  staff details (see privacy notes below). They are not used by any calculation.
  Pass this flag only if you need them for your own downstream review.
- `--check-only` — just validate field counts of a file and report problems.
- `--output-dir` — write outputs somewhere other than the current directory.

## Estimation methods

### Stratified estimation
Groups items by **publication decade** and **shelving location**. For each
group it calculates the average and standard deviation of known item costs,
applies that average to all items in the group, combines group estimates into
a total, and computes a **95% confidence interval** from the variance.

### Simple average estimation
Applies the overall average item cost to all items — useful as a comparison.

### Notes about sample sizes
- `n` = number of items with cost data in a group
- Groups with `n = 0` are excluded from the stratified estimate
- The more cost data available per group, the narrower the confidence interval

## Data handling and privacy

- **Never commit data files to this repository.** Raw exports, cleaned files,
  reports, CSVs, and charts are all gitignored (`.txt`, `.csv`, `.png` — the
  synthetic test fixture in `tests/data/` is the only exception). Before
  pushing, `git ls-files` should show no data files.
- **Item notes are stripped by default.** WMS note fields can contain patron
  record numbers from fine/billing history, donor names, and staff workflow
  notes. Library circulation records are confidential; prep removes these
  fields at the front of the pipeline so downstream files never contain them.
- **Valuation reports identify your library.** Treat `*_valuation_report.txt`
  and `*_item_estimates.csv` as internal documents.
- **OCLC data policies.** Bulk WorldCat-derived records are subject to OCLC's
  record-use policies — another reason exports must never be published.
- **No credentials.** This tool takes a file path and never connects to
  anything. Credentials for downloading reports belong in
  [wms-circ-tools](https://github.com/appalachian-college-association/wms-circ-tools),
  in a local `.env` that is never committed there either.

## Development

```powershell
pip install -e .[dev]
pytest          # run the test suite (uses the synthetic fixture in tests/data/)
ruff check .    # lint
```

## Troubleshooting

- **"File is missing expected header"** — the export's columns don't match the
  expected 31-column Circulation Item Inventories layout. Re-request the
  standard report, or compare your header against `cve/fields.py`.
- **Malformed lines reported** — see `{LIB}_inventory-errors.txt` for the exact
  lines and their field counts; these are excluded from analysis.
- **A chart window blocks the terminal** — only happens with `--show`; omit it
  and use the saved PNG instead.

## Ideas / future work

- Stratification by Dewey (or LC) classification range in addition to decade
  and location.

## Questions?

**Angie Griffin**, Systems Librarian, Appalachian College Association —
angie.griffin@acaweb.org

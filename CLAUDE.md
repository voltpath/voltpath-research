# Repo conventions

- Use en dashes (`&ndash;` in markdown/notebooks, `–` in plain text), never em dashes (`&mdash;`/`—`).
- Every notebook's charts get written to disk via `common.save_chart(fig, name)` (in addition to `fig.show()`), landing in `output/` inside that article's folder, never `media/`. `articles/*/output/` is gitignored - these are reproducible run artifacts, not published assets. `media/` is only for images actually embedded in the notebook's markdown cells (e.g. dashboard screenshots).
- No timestamp in the filename. `name` should bake in whatever the cell lets the user vary (selected month, border, date range, etc.) so re-running with the same selection overwrites the same file instead of piling up duplicates.

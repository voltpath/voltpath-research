# Voltpath Research

Research articles on European power grid data (ENTSO-E), each shipped as a single Jupyter notebook: narrative and analysis together, no separate write-up.

## Reading an article

Each article lives in `articles/<slug>/`:

- `<slug>.ipynb` – the article. Markdown cells carry the narrative, code cells run the analysis.
- `media/` – reference screenshots of the notebook's expected output, since cell outputs aren't committed (see below).

Open the notebook and run it top to bottom. You'll need your own Voltpath API key (free – sign up at [voltpath.ai](https://voltpath.ai)) pasted into the first code cell; this calls the live Voltpath API, so the data you see is current, not a frozen snapshot.

## Running locally

```bash
uv sync
uv run jupyter lab
```

## Data source and licensing

Analyses use data from the [ENTSO-E Transparency Platform](https://transparency.entsoe.eu) via the Voltpath API. Physical flow data is CC-BY 4.0 (ENTSO-E's open data list); other series (e.g. day-ahead prices) require attribution under ENTSO-E's general reuse terms. Every article credits ENTSO-E Transparency Platform as the source.

## Contributing

Cell outputs must be stripped before committing – a pre-commit hook (`nbstripout`) enforces this. Install hooks once:

```bash
uv run pre-commit install
```

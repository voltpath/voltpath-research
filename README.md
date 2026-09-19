# Voltpath Research

Research articles on European power grid data (ENTSO-E), each shipped as a single Jupyter notebook: narrative and analysis together, no separate write-up.

## Articles

- [`bertellis-flow-diagnostics/`](articles/bertellis-flow-diagnostics/) – reproduces Iacopo Bertelli's counter-intuitive flows analysis, plus a counter-intuitive flow leaderboard.

Shared fetch/analysis helpers live in [`articles/common.py`](articles/common.py) – read it if you want to see exactly how flow types, costs, and leaderboards are computed.

## Reading an article

Each article lives in `articles/<slug>/`:

- an `.ipynb` notebook – the article. Markdown cells carry the narrative, code cells run the analysis.
- `media/` – reference screenshots of the notebook's expected output, since cell outputs aren't committed (see below).

Open the notebook and run it top to bottom. You'll need your own Voltpath API key (free – sign up at [voltpath.ai](https://voltpath.ai); once logged in, copy your key any time from [voltpath.ai/settings](https://voltpath.ai/settings)). Notebooks call the live Voltpath API, so the data you see is current, not a frozen snapshot – responses are cached to disk under `articles/.cache/` so re-running a notebook doesn't re-fetch data you already have.

API docs live at [docs.voltpath.ai](https://docs.voltpath.ai). If you're using an AI coding agent with the Context7 MCP server, it can pull these docs directly instead of guessing at endpoint shapes.

## Running locally

```bash
cp .env.example .env   # paste your API key into VOLTPATH_API_KEY
uv sync
uv run jupyter lab
```

Leave `.env` empty and the notebook prompts for the key instead.

## Data source and licensing

Analyses use data from the [ENTSO-E Transparency Platform](https://transparency.entsoe.eu) via the Voltpath API. Physical flow data is CC-BY 4.0 (ENTSO-E's open data list); other series (e.g. day-ahead prices) require attribution under ENTSO-E's general reuse terms. Every article credits ENTSO-E Transparency Platform as the source.

## Contributing

Cell outputs must be stripped before committing – a pre-commit hook (`nbstripout`) enforces this. Install hooks once:

```bash
uv run pre-commit install
```

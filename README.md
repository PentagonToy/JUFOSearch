# JUFOSearch

**[Open JUFOSearch ↗](https://jufosearch.vercel.app/)**

Find journals by title, ISSN, initials or research keywords. Compare JUFO levels and history, OpenAlex-derived quartiles, Aalto APC support and OA publishing routes for your institution and funder.

## Develop locally

Python 3.12 or later; no Python packages to install. Node.js is needed only for the browser-logic tests.

```sh
python3.12 -B server.py
python3.12 -B -m unittest discover -s tests -q
node --test tests/*.cjs
```

Open [localhost:8765](http://127.0.0.1:8765/). Vercel serves `public/` and the Python handlers in `api/`. Data-refresh tools live in `scripts/`; tests live in `tests/`.

[Setup, data and deployment](docs/guide.md) · [Quartile method](docs/metrics.md) · [Similar journals](docs/recommendations.md)

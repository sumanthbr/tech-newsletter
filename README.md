# Daily Tech Flash Brief

Static, free-hostable portal for daily updates across:
- GenAI
- Azure
- GCP
- AWS
- Industry news

The UI is flash-card style: short summary first, expandable details, and a source link.

## Project structure
- `src/`: static website (HTML/CSS/JS)
- `scripts/build_digest.py`: OPML + RSS/Atom to digest JSON builder
- `src/data/sample-feeds.json`: generated story feed consumed by UI
- `.github/workflows/daily-digest.yml`: daily auto-refresh workflow

## Run locally
From project root:

```powershell
python scripts/build_digest.py --opml Feeder-2026-02-28.opml --output src/data/sample-feeds.json
cd src
python -m http.server 5500
```

Open `http://localhost:5500`.

## Generate your daily brief
Use your exported Feeder OPML:

```powershell
python scripts/build_digest.py --opml Feeder-2026-02-28.opml --output src/data/sample-feeds.json --max-stories 45 --days 2
```

What it does:
1. Reads all RSS URLs from OPML.
2. Fetches feed entries.
3. Auto-tags each story (GenAI/Azure/GCP/AWS/Industry).
4. Creates summary + quick details for each card.
5. Writes sorted cards into `src/data/sample-feeds.json`.

## Free hosting options
1. GitHub Pages (recommended)
2. Netlify
3. Cloudflare Pages

## GitHub Pages setup
1. Push this repo to GitHub.
2. In repo settings, open `Pages`.
3. Set source to `Deploy from a branch`.
4. Select branch `main` and folder `/src`.
5. Save.

## Daily auto refresh (free)
Workflow already included: `.github/workflows/daily-digest.yml`.

It runs daily (`02:35 UTC`) and on manual trigger. The workflow:
1. Builds latest digest JSON from your OPML feeds.
2. Commits updated `src/data/sample-feeds.json`.
3. Pushes to `main` so your hosted site updates automatically.

If your OPML filename changes, update the `--opml` value in the workflow.

## Notes
- Some feeds may fail occasionally (timeout/CORS/old URL); script skips failed feeds.
- Summaries are lightweight heuristic summaries from feed text.
- For higher quality summaries, next step is adding an LLM call in `scripts/build_digest.py`.

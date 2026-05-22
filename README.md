https://github.com/user-attachments/assets/c48506d0-8be4-4a5c-815e-7e50a56a0dd0

# hamplanet

Playwright-driven Rumble downvote automation, aimed squarely at the ham planet (quarter pounders) channels. Point it at a list of channels, walk away, come back to a wall of red thumbs.

## Features

- **Multi-channel** — drive any list of Rumble channels from `channels.json`.
- **Videos + shorts** — each channel run does a videos pass and a shorts pass by default (`--mode` narrows it).
- **Stateful** — SQLite log of every URL acted on (`hamplanet.db`); future runs skip them automatically.
- **Auth-aware** — caches a Playwright `storage_state.json` so you log in once.
- **Polite-ish pacing** — randomized 4-6s sleep between items (tunable; bumped from 3s after hitting Rumble's vote rate limit).
- **Dry-run by default** — see the targets before anything clicks.
- **Per-channel limit** — `--limit N` applies per pass per channel, ideal for smoke tests across the whole roster.
- **Resumable** — Ctrl-C, come back later; the DB picks up where you left off.

## Setup

Install [uv](https://docs.astral.sh/uv/) (the only prerequisite — it handles Python and the venv):

```sh
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# or via Homebrew
brew install uv

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then bootstrap the project:

```sh
uv sync
uv run playwright install chromium
cp .env.example .env   # fill in RUMBLE_USERNAME / RUMBLE_PASSWORD
```

Edit [channels.json](channels.json):

```json
{
  "channels": [
    "https://rumble.com/c/JeremyHambly",
    "https://rumble.com/c/TheQuartering",
    "https://rumble.com/c/UnSleevedMedia"
  ]
}
```

Requires Python 3.14+. uv will install it in a venv if you don't have it globally.

## Quick reference

### Common runs

```sh
# Dry-run across every channel — no clicks, just shows what would happen.
# Default mode is "both": videos pass then shorts pass per channel.
uv run hamplanet

# Smoke test: 2 videos + 2 shorts per channel, real clicks.
uv run hamplanet --execute --limit 2

# Full sweep, real clicks (videos + shorts).
uv run hamplanet --execute

# Videos only (old default behavior).
uv run hamplanet --mode videos --execute

# Shorts only — handy for backfilling shorts after a videos-only run.
uv run hamplanet --mode shorts --execute

# Scrape-only — list every discovered URL, no per-item visits.
uv run hamplanet --no-auth --limit 0

# Watch it work.
uv run hamplanet --execute --headed
```

### All flags

| Flag | Default | What it does |
|---|---|---|
| `--config PATH` | `channels.json` | Channel list JSON |
| `--mode {videos,shorts,both}` | `both` | Which content type(s) to process per channel |
| `--execute` | off | Actually click (without it, run is a dry-run) |
| `--limit N` | none | Process at most N items **per pass per channel**; `0` = scrape-only |
| `--headed` | off | Show the browser window |
| `--min-delay` / `--max-delay` | 4.0 / 6.0 | Random sleep range between items (seconds) |
| `--login` | off | Force a fresh login even if `storage_state.json` exists |
| `--storage PATH` | `storage_state.json` | Playwright session file |
| `--no-auth` | off | Skip login (dry-runs against the public site) |
| `--db PATH` | `hamplanet.db` | SQLite state DB |
| `--ignore-state` | off | Don't skip URLs already in the DB |

### Vote results

| Result | Meaning | Recorded in DB? |
|---|---|---|
| `CLICKED` | Successfully downvoted | yes |
| `ALREADY_DOWN` | You'd already downvoted this video | yes |
| `WOULD_CLICK` | Dry-run: button found, not clicked | no |
| `NOT_FOUND` | Downvote button never appeared (deleted/private/page error) | no |
| `AUTH_REQUIRED` | Session went anonymous mid-run — re-run with `--login` | no |

### Inspecting state

The DB is plain SQLite — one row per acted-on URL. Videos and shorts share the same `actions` table; the URL itself tells them apart (shorts contain `/shorts/`).

```sh
# Total acted-on
sqlite3 hamplanet.db "SELECT COUNT(*) FROM actions;"

# Per channel
sqlite3 hamplanet.db "SELECT channel, COUNT(*) FROM actions GROUP BY channel;"

# Breakdown by result
sqlite3 hamplanet.db "SELECT result, COUNT(*) FROM actions GROUP BY result;"

# Videos vs shorts
sqlite3 hamplanet.db \
  "SELECT CASE WHEN url LIKE '%/shorts/%' THEN 'short' ELSE 'video' END AS kind,
          COUNT(*) FROM actions GROUP BY kind;"

# Most recent 10
sqlite3 hamplanet.db \
  "SELECT created_at, channel, result, url FROM actions
   ORDER BY created_at DESC LIMIT 10;"

# Wipe state for one channel (re-process from scratch)
sqlite3 hamplanet.db "DELETE FROM actions WHERE channel='JeremyHambly';"

# Reset everything (nuclear)
rm hamplanet.db
```

### Schema

```
actions(url PK, site, channel, action, result, created_at)
```

`url` is the primary key, so re-runs are idempotent. Shorts (`/shorts/v...`) and regular videos (`/v...-title.html`) live in distinct URL namespaces and never collide. `site` + `channel` are columns (not part of the PK) to leave room for adding YouTube or other sites alongside Rumble.

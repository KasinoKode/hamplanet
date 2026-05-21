https://github.com/user-attachments/assets/c48506d0-8be4-4a5c-815e-7e50a56a0dd0

# hamplanet

Playwright-driven Rumble downvote automation, aimed squarely at the ham planet (quarter pounders) channels. Point it at a list of channels, walk away, come back to a wall of red thumbs.

## Features

- **Multi-channel** — drive any list of Rumble channels from `channels.json`.
- **Stateful** — SQLite log of every URL acted on (`hamplanet.db`); future runs skip them automatically.
- **Auth-aware** — caches a Playwright `storage_state.json` so you log in once.
- **Polite-ish pacing** — randomized 3-6s sleep between videos (tunable).
- **Dry-run by default** — see the targets before anything clicks.
- **Per-channel limit** — `--limit N` applies per channel, ideal for smoke tests across the whole roster.
- **Resumable** — Ctrl-C, come back later; the DB picks up where you left off.

## Setup

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
uv run hamplanet

# Smoke test: 2 videos per channel, real clicks.
uv run hamplanet --execute --limit 2

# Full sweep, real clicks.
uv run hamplanet --execute

# Scrape-only — list every discovered URL, no per-video visits.
uv run hamplanet --no-auth --limit 0

# Watch it work.
uv run hamplanet --execute --headed
```

### All flags

| Flag | Default | What it does |
|---|---|---|
| `--config PATH` | `channels.json` | Channel list JSON |
| `--execute` | off | Actually click (without it, run is a dry-run) |
| `--limit N` | none | Process at most N videos **per channel**; `0` = scrape-only |
| `--headed` | off | Show the browser window |
| `--min-delay` / `--max-delay` | 3.0 / 6.0 | Random sleep range between videos (seconds) |
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

The DB is plain SQLite — one row per acted-on URL.

```sh
# Total acted-on
sqlite3 hamplanet.db "SELECT COUNT(*) FROM actions;"

# Per channel
sqlite3 hamplanet.db "SELECT channel, COUNT(*) FROM actions GROUP BY channel;"

# Breakdown by result
sqlite3 hamplanet.db "SELECT result, COUNT(*) FROM actions GROUP BY result;"

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

`url` is the primary key, so re-runs are idempotent. `site` + `channel` are columns (not part of the PK) to leave room for adding YouTube or other sites alongside Rumble.

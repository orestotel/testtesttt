# OpenDota match summary

`opendota_match.py` fetches any OpenDota match and writes two files:

- `match_<id>.json` — the **complete** raw OpenDota match data (everything the API returns)
- `match_<id>.txt`  — a clean summary (also printed to the terminal)

The summary includes, per player: hero, K/D/A, net worth, GPM/XPM, lane, and items;
plus team net-worth totals, the winner, and the **net-worth-advantage curve**
(Radiant gold lead per minute, with peaks and an ASCII chart).

## Usage

```bash
python3 opendota_match.py 8857059540
# or pick an output directory
python3 opendota_match.py 8857059540 --outdir ./out
```

Swap `8857059540` for any match id. Only the Python 3 standard library is required
(no API key for public matches).

## Note on this remote environment

This Claude Code session runs in a sandboxed container whose network egress
allowlist does **not** include `api.opendota.com`, so the live data couldn't be
fetched from here (requests return `403 / Host not in allowlist`). Run the script
on your own machine, or add `api.opendota.com` to the environment's network egress
settings, and it will produce both files.

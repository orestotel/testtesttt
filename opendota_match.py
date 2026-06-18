#!/usr/bin/env python3
"""
opendota_match.py — Fetch an OpenDota match and produce a clean summary + a full data dump.

Usage:
    python3 opendota_match.py <match_id> [--outdir DIR]

Examples:
    python3 opendota_match.py 8857059540
    python3 opendota_match.py 8857059540 --outdir ./out

Outputs (written to --outdir, default current directory):
    match_<id>.json      -> the COMPLETE raw OpenDota match JSON (all the data)
    match_<id>.txt       -> the human-readable summary (also printed to stdout)

Requires only the Python 3 standard library. Needs outbound network access to
https://api.opendota.com (no API key required for public matches).
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

API = "https://api.opendota.com/api"
# A browser-like UA helps get past OpenDota's bot protection from some hosts.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

LANE_ROLE = {1: "Safe", 2: "Mid", 3: "Off", 4: "Jungle"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def fmt_int(n):
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "?"


def hms(seconds):
    if seconds is None:
        return "?"
    seconds = int(seconds)
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    return f"{sign}{seconds // 60}:{seconds % 60:02d}"


def build_summary(m, heroes, items):
    def hero_name(hid):
        h = heroes.get(str(hid)) or heroes.get(hid)
        if not h:
            return f"hero_{hid}"
        return h.get("localized_name") or h.get("name", f"hero_{hid}").replace("npc_dota_hero_", "")

    def item_name(iid):
        if not iid:  # 0 / None == empty slot
            return None
        it = items.get(str(iid)) or items.get(iid)
        if not it:
            return f"item_{iid}"
        return it.get("dname") or it.get("name", f"item_{iid}")

    lines = []
    mid = m.get("match_id")
    radiant_win = m.get("radiant_win")
    winner = "Radiant" if radiant_win else "Dire"
    dur = m.get("duration")

    lines.append(f"OpenDota Match {mid}")
    lines.append("=" * 60)
    lines.append(f"Duration : {hms(dur)}")
    lines.append(f"Score    : Radiant {m.get('radiant_score','?')} - {m.get('dire_score','?')} Dire")
    lines.append(f"WINNER   : {winner}")
    if m.get("league") or m.get("leagueid"):
        lines.append(f"League   : {(m.get('league') or {}).get('name', m.get('leagueid'))}")
    lines.append("")

    players = m.get("players", [])
    radiant = [p for p in players if p.get("isRadiant", (p.get("player_slot", 0) < 128))]
    dire = [p for p in players if not p.get("isRadiant", (p.get("player_slot", 0) < 128))]

    def player_block(team_name, team):
        team_nw = 0
        out = [f"--- {team_name} ---"]
        header = f"{'Hero':<18}{'Player':<16}{'K/D/A':<10}{'NW':>8}{'GPM':>6}{'XPM':>6}  {'Lane':<7}"
        out.append(header)
        out.append("-" * len(header))
        for p in team:
            nw = p.get("net_worth") or p.get("total_gold") or 0
            team_nw += nw or 0
            kda = f"{p.get('kills',0)}/{p.get('deaths',0)}/{p.get('assists',0)}"
            name = (p.get("personaname") or p.get("name") or
                    (f"acct_{p.get('account_id')}" if p.get("account_id") else "Anonymous"))
            lane = LANE_ROLE.get(p.get("lane_role"), "?")
            if p.get("is_roaming"):
                lane = "Roam"
            out.append(
                f"{hero_name(p.get('hero_id')):<18}{name[:15]:<16}{kda:<10}"
                f"{fmt_int(nw):>8}{p.get('gold_per_min','?'):>6}{p.get('xp_per_min','?'):>6}  {lane:<7}"
            )
            slots = [p.get(f"item_{i}") for i in range(6)]
            item_names = [item_name(s) for s in slots]
            item_names = [n for n in item_names if n]
            backpack = [item_name(p.get(f"backpack_{i}")) for i in range(3)]
            backpack = [n for n in backpack if n]
            neutral = item_name(p.get("item_neutral"))
            items_str = ", ".join(item_names) if item_names else "(none)"
            extra = ""
            if backpack:
                extra += f"  | backpack: {', '.join(backpack)}"
            if neutral:
                extra += f"  | neutral: {neutral}"
            out.append(f"    items: {items_str}{extra}")
        out.append("")
        out.append(f"  {team_name} total net worth: {fmt_int(team_nw)}")
        out.append("")
        return out, team_nw

    rblock, r_nw = player_block("RADIANT", radiant)
    dblock, d_nw = player_block("DIRE", dire)
    lines += rblock
    lines += dblock

    lines.append("=== Team net worth ===")
    lines.append(f"  Radiant : {fmt_int(r_nw)}")
    lines.append(f"  Dire    : {fmt_int(d_nw)}")
    diff = r_nw - d_nw
    leader = "Radiant" if diff >= 0 else "Dire"
    lines.append(f"  Lead    : {leader} +{fmt_int(abs(diff))}")
    lines.append("")

    # Net-worth-advantage curve (Radiant minus Dire gold, per minute).
    adv = m.get("radiant_gold_adv")
    if adv:
        lines.append("=== Net-worth advantage curve (Radiant gold lead, per minute) ===")
        lines.append("  positive = Radiant ahead, negative = Dire ahead")
        peak_r = max(adv)
        peak_d = min(adv)
        lines.append(f"  Radiant peak: +{fmt_int(peak_r)} @ {adv.index(peak_r)}:00   "
                     f"Dire peak: +{fmt_int(-peak_d)} @ {adv.index(peak_d)}:00")
        lines.append("")
        # Compact ASCII sparkline + a sampled table.
        blocks = "▁▂▃▄▅▆▇█"
        lo, hi = min(adv), max(adv)
        span = (hi - lo) or 1
        spark = "".join(blocks[min(7, int((v - lo) / span * 7))] for v in adv)
        lines.append("  " + spark)
        lines.append("")
        lines.append(f"  {'min':>4} | {'Radiant adv':>12} | bar")
        lines.append("  " + "-" * 40)
        step = max(1, len(adv) // 30)  # cap rows so long games stay readable
        for i in range(0, len(adv), step):
            v = adv[i]
            barlen = int(min(20, abs(v) / (max(abs(hi), abs(lo)) or 1) * 20))
            bar = ("+" * barlen) if v >= 0 else ("-" * barlen)
            lines.append(f"  {i:>4} | {fmt_int(v):>12} | {bar}")
        # always show final minute
        if (len(adv) - 1) % step != 0:
            i = len(adv) - 1
            v = adv[i]
            barlen = int(min(20, abs(v) / (max(abs(hi), abs(lo)) or 1) * 20))
            bar = ("+" * barlen) if v >= 0 else ("-" * barlen)
            lines.append(f"  {i:>4} | {fmt_int(v):>12} | {bar}")
    else:
        lines.append("(No radiant_gold_adv data — match may be unparsed. "
                     "Request a parse on opendota.com and retry.)")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="OpenDota match summary + full data dump")
    ap.add_argument("match_id", help="Dota 2 / OpenDota match id")
    ap.add_argument("--outdir", default=".", help="output directory (default: .)")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    try:
        match = get(f"{API}/matches/{args.match_id}")
    except urllib.error.HTTPError as e:
        sys.exit(f"Failed to fetch match {args.match_id}: HTTP {e.code} {e.reason}")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Failed to fetch match {args.match_id}: {e}")

    # Constants for human-readable hero/item names. Best-effort; summary still works without.
    heroes, items = {}, {}
    try:
        heroes = get(f"{API}/constants/heroes")
    except Exception:
        pass
    try:
        items = get(f"{API}/constants/items")
        # constants/items is keyed by name; remap to id for lookup
        items = {str(v.get("id")): v for v in items.values() if isinstance(v, dict) and "id" in v}
    except Exception:
        items = {}

    raw_path = os.path.join(args.outdir, f"match_{args.match_id}.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(match, f, indent=2, ensure_ascii=False)

    summary = build_summary(match, heroes, items)
    txt_path = os.path.join(args.outdir, f"match_{args.match_id}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(summary + "\n")

    print(summary)
    print()
    print(f"[+] Full raw data : {raw_path}")
    print(f"[+] Summary       : {txt_path}")


if __name__ == "__main__":
    main()

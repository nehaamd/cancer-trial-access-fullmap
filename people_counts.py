"""Exact counts of residents 55+ below a trial-count line, by nation, state and congressional district.

Pages and the data API printed some of these as population x the share rounded to one decimal. For a small share that is far off:
Virginia's 0.1% "with no trial within 60 road-miles" printed as 2,568 people where the census tracts sum to 3,812. The map's state
and national panels already used tract sums. This module gives every builder the same tract sums, from the table the shares come from
(out_adult55/tract_access.csv), apportioning a tract split between districts by its share of residents 55+ (data/ref/tract_cd119.csv),
which is how the district shares themselves are computed.

    counts = exact_counts()
    counts["nat"]                -> {"p": ..., "l20": ..., "z60": ...}
    counts["state"]["51"]        -> the same, by state FIPS
    counts["district"]["5600"]   -> the same, by district geoid

pick(exact, pop, share) returns the exact count when it agrees with the published share (so a table from another run is never
used), and otherwise the old rounded figure.
"""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def exact_counts(tracts=None, rel=None):
    tracts = Path(tracts or ROOT / "out_adult55" / "tract_access.csv"); rel = Path(rel or ROOT / "data" / "ref" / "tract_cd119.csv")
    z = lambda: {"p": 0.0, "l20": 0.0, "z60": 0.0}
    nat, state, district = z(), defaultdict(z), defaultdict(z)
    if not tracts.exists(): return {"nat": None, "state": {}, "district": {}}
    shares = defaultdict(list)
    if rel.exists():
        with open(rel, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh): shares[r["tract"]].append((r["cd_geoid"], float(r["share"])))
    with open(tracts, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            p = float(r["pop55"] or 0); t = float(r["trials_within_60rdmi"] or 0)
            v = {"p": p, "l20": p if t < 20 else 0.0, "z60": p if t == 0 else 0.0}
            for tgt in (nat, state[r["county_fips"][:2]]):
                for k in v: tgt[k] += v[k]
            for cd, sh in shares.get(r["tract"], ()):
                for k in v: district[cd][k] += v[k] * sh
    rnd = lambda d: {k: int(round(x)) for k, x in d.items()}
    return {"nat": rnd(nat), "state": {k: rnd(v) for k, v in state.items()}, "district": {k: rnd(v) for k, v in district.items()}}


def pick(exact, pop, share):
    """The exact count when it matches the published share to rounding; else population x share, rounded (the earlier rule)."""
    if share is None or pop is None: return None
    rounded = int(round(pop * share / 100))
    if exact is None or not pop: return rounded
    return int(exact) if abs(100 * exact / pop - share) <= 0.06 else rounded


if __name__ == "__main__":
    c = exact_counts(); print("nation", c["nat"]); print("Virginia", c["state"].get("51")); print("WY-AL", c["district"].get("5600"), "| districts", len(c["district"]))

#!/usr/bin/env python3
"""Plain-language summaries and tags for each listed trial, generated once per record by an AI model, offline, in the weekly refresh.

For every trial in the published set (docs/data.js, T.id) the script sends the registry text (title, official title, conditions, keywords,
interventions and their descriptions, arm descriptions, brief summary, eligibility criteria when the pull carries them, ages, phase, sponsor)
to the model and asks for one JSON object: a three-sentence summary in English and in Spanish, "who the study team says it is for" and
"who it is not for" as short paraphrases of the stated criteria, and tags (cancer types, biomarkers, route of the study drug). The model is
told to use only the text given and to write "not stated" rather than guess. Nothing is generated live on the site.

Results are cached in data/ref/trial_summaries.json keyed by NCT id and the record's last-update date, so a weekly run only calls the model
for trials that are new or whose record changed. Outputs:
    docs/api/trial/NCT0....json   one file per trial (the ZIP finder fetches it when a reader opens "Plain-language summary")
    docs/api/trials_index.json    counts, model, dates
The script never stops the refresh: with no ANTHROPIC_API_KEY it writes what the cache holds and says so; API errors are logged and the
trial is retried next week. Set SUMMARY_MODEL to change the model (default claude-haiku-5-5) and SUMMARY_LIMIT to cap calls in one run.
"""
import json, os, sys, time, datetime, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
CACHE = ROOT / "data" / "ref" / "trial_summaries.json"
OUT = ROOT / "docs" / "api" / "trial"
MODEL = os.environ.get("SUMMARY_MODEL", "claude-haiku-5-5")
LIMIT = int(os.environ.get("SUMMARY_LIMIT", "0") or 0)
WORKERS = int(os.environ.get("SUMMARY_WORKERS", "4") or 4)
# The reply budget. It was 900 tokens, and on 16 and 17 Nov 2026 every call came back with no text at all, or with text cut off inside
# the first sentence ("Expecting value: line 1 column 1", "Unterminated string"): the budget was used up before the answer was
# written. The answer itself is about 500 tokens; the rest of the budget is headroom for whatever the model produces before it. A
# reply that stops at the budget, or carries no text, is now reported as that (reply_text) instead of as a JSON error, and the
# second attempt gets twice the budget.
MAX_TOKENS = int(os.environ.get("SUMMARY_MAX_TOKENS", "4000") or 4000)


def reply_text(msg):
    """The text of a reply, or a ValueError that says why there is none (so the run log names the cause)."""
    text = "".join(getattr(b, "text", "") or "" for b in (msg.content or []) if getattr(b, "type", "") == "text")
    stop = getattr(msg, "stop_reason", None)
    if not text.strip() or stop == "max_tokens":
        kinds = ", ".join(sorted({str(getattr(b, "type", "?")) for b in (msg.content or [])})) or "none"
        used = getattr(getattr(msg, "usage", None), "output_tokens", "?")
        raise ValueError(f"no complete answer: stop_reason {stop}, {used} output tokens, content blocks: {kinds}")
    return text
# A time budget and a give-up rule, so this optional step can never use up the refresh job's time limit: the manual refresh of 5 Nov 2026
# was cancelled at 90 minutes inside this step (every call failed, each failure waited and retried, about 4,000 trials were queued) and
# nothing was published. Whatever is not written this run is picked up by the next one.
MINUTES = float(os.environ.get("SUMMARY_MINUTES", "20") or 20)
GIVE_UP_AFTER = int(os.environ.get("SUMMARY_GIVE_UP_AFTER", "25") or 25)   # consecutive failures
VERSION = "1"   # bump to regenerate every summary (prompt or schema change)

SYSTEM = """You write plain-language summaries of cancer clinical trial registry records for patients, families and patient navigators.
Rules you must follow:
- Use ONLY the record text you are given. Do not add medical knowledge, outcomes, benefits, risks or eligibility that the text does not state.
- If something is not in the text, write "not stated". Never guess.
- Do not advise. Do not say whether a trial is good, promising, or right for anyone. Do not say "you may qualify".
- Plain words, short sentences, reading level about 8th grade. Spell out drug names as given; do not invent brand names.
- "who_for" and "not_for" are short paraphrases of the stated inclusion and exclusion criteria, at most 5 each, each under 20 words, no clinical codes. If criteria are absent, return empty lists.
- Tags: cancer_types from the record's conditions (plain names, lower case, at most 6); biomarkers only if a gene, protein or marker is named as part of eligibility or the trial's target (upper-case symbols like KRAS, HER2, EGFR, PD-L1, MSI-H; at most 6); route is how the study drug is given: one of oral, infusion, injection, radiation, surgery, procedure, mixed, none, not stated.
- Answer with one JSON object only, no prose before or after, with keys: summary_en, summary_es, who_for, not_for, cancer_types, biomarkers, route.
- summary_en: exactly three sentences: (1) what is being tested and in which cancer, (2) how it is given and how long or how often if stated, (3) what the study measures (the main outcome) if stated, else what phase it is. summary_es: the same three sentences in neutral Latin American Spanish."""

def load_js(name):
    s = (ROOT / "docs" / name).read_text(encoding="utf-8")
    return json.loads(s.split("=", 1)[1].strip().rstrip(";"))

def dig(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict): return default
        d = d.get(k)
    return d if d is not None else default

def record_text(ps):
    """The fields a reader would use, as labelled text, capped so one record stays well under the model's limits."""
    idm, desc, cond, arms, elig, design, spons = (ps.get(k, {}) for k in ("identificationModule", "descriptionModule", "conditionsModule", "armsInterventionsModule", "eligibilityModule", "designModule", "sponsorCollaboratorsModule"))
    ivs = arms.get("interventions") or []
    parts = [
        ("Title", idm.get("briefTitle")), ("Official title", idm.get("officialTitle")),
        ("Conditions", "; ".join(cond.get("conditions") or [])), ("Keywords", "; ".join(cond.get("keywords") or [])),
        ("Phase", "/".join(design.get("phases") or []) or "not stated"),
        ("Sponsor", dig(spons, "leadSponsor", "name")),
        ("Interventions", " | ".join(f"{i.get('type','')}: {i.get('name','')}" + (f" — {i.get('description','')}" if i.get("description") else "") for i in ivs)),
        ("Arms", " | ".join(f"{a.get('label','')}: {a.get('description','')}" for a in (arms.get("armGroups") or []) if a.get("description"))),
        ("Brief summary", desc.get("briefSummary")),
        ("Ages", f"{elig.get('minimumAge') or 'not stated'} to {elig.get('maximumAge') or 'no upper limit stated'}"),
        ("Eligibility criteria", elig.get("eligibilityCriteria")),
    ]
    txt = "\n".join(f"{k}: {str(v).strip()}" for k, v in parts if v)
    return txt[:12000]

def row_text(r):
    """Fallback when the raw registry file is not present: the columns of trials.csv."""
    parts = [("Title", r.get("brief_title")), ("Official title", r.get("official_title")), ("Conditions", r.get("conditions")), ("Keywords", r.get("keywords")),
             ("Phase", r.get("phases")), ("Sponsor", r.get("lead_sponsor")), ("Interventions", f"{r.get('intervention_types','')}: {r.get('intervention_names','')}"),
             ("Ages", f"{r.get('minimum_age') or 'not stated'} to {r.get('maximum_age') or 'no upper limit stated'}")]
    return "\n".join(f"{k}: {str(v).strip()}" for k, v in parts if v)[:12000]

def parse_json(s):
    s = s.strip()
    m = re.search(r"\{.*\}", s, re.S)
    obj = json.loads(m.group(0) if m else s)
    out = {"summary_en": str(obj.get("summary_en", "")).strip(), "summary_es": str(obj.get("summary_es", "")).strip(),
           "who_for": [str(x)[:160] for x in (obj.get("who_for") or [])][:5], "not_for": [str(x)[:160] for x in (obj.get("not_for") or [])][:5],
           "cancer_types": [str(x).lower()[:60] for x in (obj.get("cancer_types") or [])][:6], "biomarkers": [str(x)[:30] for x in (obj.get("biomarkers") or [])][:6],
           "route": str(obj.get("route", "not stated")).lower()[:20]}
    if not out["summary_en"] or not out["summary_es"]: raise ValueError("empty summary")
    return out

def main():
    D = load_js("data.js"); ids = D["T"]["id"]; upd = D["T"]["upd"]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    # registry text: the raw pull when present (brief summary, arms, eligibility), else trials.csv
    raw = {}
    if (RAW / "studies_raw.jsonl").exists():
        with open(RAW / "studies_raw.jsonl", encoding="utf-8") as fh:
            for line in fh:
                try: st = json.loads(line)
                except ValueError: continue
                ps = st.get("protocolSection", st); n = dig(ps, "identificationModule", "nctId")
                if n: raw[n] = record_text(ps)
    rows = {}
    if not raw:
        import csv
        with open(RAW / "trials.csv", newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh): rows[r["nct_id"]] = row_text(r)
    todo = [(n, u) for n, u in zip(ids, upd) if not (cache.get(n) and cache[n].get("upd") == u and cache[n].get("v") == VERSION)]
    print(f"summaries: {len(ids)} listed trials, {len(ids) - len(todo)} already summarised, {len(todo)} to generate (source: {'registry records' if raw else 'trials.csv'})")
    key = os.environ.get("ANTHROPIC_API_KEY")
    if todo and not key:
        print("summaries: ANTHROPIC_API_KEY is not set; writing cached summaries only. Add the key as a repository secret to generate the rest.")
        todo = []
    if LIMIT and len(todo) > LIMIT: todo = todo[:LIMIT]; print(f"summaries: capped at {LIMIT} this run (SUMMARY_LIMIT)")
    if todo:
        try:
            import anthropic
        except ImportError:
            print("summaries: the anthropic package is not installed (pip install anthropic); writing cached summaries only."); todo = []
    done = failed = 0
    if todo:
        client = anthropic.Anthropic(api_key=key)
        import threading
        stop = threading.Event(); deadline = time.time() + 60 * MINUTES; streak = 0; left = 0; why = ""
        def one(n, u):
            if stop.is_set() or time.time() > deadline: stop.set(); return n, u, None, "left for the next run"
            text = raw.get(n) or rows.get(n)
            if not text: return n, u, None, "no record text"
            errs = []
            for attempt in (1, 2):
                try:
                    msg = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS * attempt, system=SYSTEM,
                                                 messages=[{"role": "user", "content": f"Registry record {n}:\n\n{text}\n\nReturn the JSON object."}])
                    return n, u, parse_json(reply_text(msg)), None
                except Exception as e:   # rate limits, transient errors, a reply cut short, malformed JSON: once more, then leave it for next week
                    errs.append(f"{type(e).__name__}: {str(e)[:160]}"); time.sleep(2 * attempt)
            return n, u, None, " | then: ".join(errs)
        today = datetime.date.today().isoformat()
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(one, n, u) for n, u in todo]
            for f in as_completed(futs):
                n, u, res, err = f.result()
                if res: cache[n] = {"upd": u, "v": VERSION, "model": MODEL, "generated": today, **res}; done += 1; streak = 0
                elif err == "left for the next run": left += 1; why = why or f"the {MINUTES:g}-minute budget was used"
                else:
                    failed += 1; streak += 1
                    if failed <= 20: print(f"summaries: {n} skipped ({err})")
                    if streak >= GIVE_UP_AFTER and not stop.is_set(): stop.set(); why = f"{GIVE_UP_AFTER} calls in a row failed (last: {err})"
                if (done + failed) % 200 == 0: print(f"summaries: {done} generated, {failed} skipped so far"); CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        if left: print(f"summaries: stopped early because {why}; {left} trials left for the next run")
        # A step that may fail without stopping the refresh must at least say so where it is seen: an annotation on the run page.
        if failed and not done: print(f"::warning title=Plain-language summaries::none written this run: all {failed} calls failed ({why or 'see the log lines above'}). The refresh is not affected; the summary expander stays hidden on the ZIP finder.")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    # ---- publish: one file per listed trial that has a summary; drop files for trials no longer listed ----
    OUT.mkdir(parents=True, exist_ok=True)
    listed = set(ids); keep = set()
    note = "Written by an AI model from the ClinicalTrials.gov record, using only that text; checked by sampling, not line by line. The study team decides who is eligible. Not medical advice."
    nota = "Escrito por un modelo de IA a partir del registro de ClinicalTrials.gov, usando solo ese texto; revisado por muestreo, no línea por línea. El equipo del estudio decide quién es elegible. No es consejo médico."
    for n in ids:
        c = cache.get(n)
        if not c: continue
        keep.add(n)
        (OUT / f"{n}.json").write_text(json.dumps({"nct_id": n, "record_updated": c["upd"], "generated": c["generated"], "model": c["model"],
            "summary_en": c["summary_en"], "summary_es": c["summary_es"], "who_for": c["who_for"], "not_for": c["not_for"],
            "cancer_types": c["cancer_types"], "biomarkers": c["biomarkers"], "route": c["route"],
            "note_en": note, "note_es": nota, "registry": f"https://clinicaltrials.gov/study/{n}"}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    for p in OUT.glob("NCT*.json"):
        if p.stem not in keep: p.unlink()
    idx = {"built": datetime.date.today().isoformat(), "listed_trials": len(ids), "with_summary": len(keep), "generated_this_run": done, "skipped_this_run": failed,
           "model": MODEL, "version": VERSION, "file": "api/trial/{NCT}.json", "note": note}
    (ROOT / "docs" / "api" / "trials_index.json").write_text(json.dumps(idx, indent=1) + "\n", encoding="utf-8")
    print(f"summaries: {len(keep)} of {len(ids)} listed trials have a summary ({done} generated, {failed} skipped this run) -> {OUT}/")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:   # never stop the refresh chain over summaries
        print(f"summaries: failed ({type(e).__name__}: {e}); the rest of the refresh is unaffected", file=sys.stderr)

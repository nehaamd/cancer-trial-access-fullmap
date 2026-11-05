# "Ask the map" helper (v3)

A small Cloudflare Worker behind the question box on the map and the homepage. It is a stateless, signed, rate-limited model
proxy with a verifier: it holds the Anthropic API key (the site's code never sees it), gives a Claude model *tools* that read the
site's data, and checks every number and place name in the model's final answer against the tool results before the site shows
it. The tools themselves run in the browser (`docs/ask/engine.js`) against the same files the map draws, so a figure in an answer
is the figure on the map. The contract for every component is `ASK_CONTRACT.md` at the repository root; this file describes the
worker's part.

## Design

```
browser (docs/ask/ask.js + engine.js)                     worker (this directory)
  question ─────────────────────────────────────────────► POST /ask {v:3, q, turns:[], prior}
                                                           limits (step 0; continuation steps capped at MAX_STEPS × those) → step(): prompt + tools from the catalog → model
  ◄──────────────────────────────── {kind:"tools", assistant, sig, calls:[{id,name,input}]}
  run every call with the engine (query / aggregate / profile / compare / find_places / trials / site_info / method)
  POST again with turns:[…, {assistant, sig, results}] ──► check the signatures, rebuild the transcript, call the model again
  …                                                        the model's final_answer → verify() against the tool results
                                                           (numbers, names, ids, style, and each figure's place: claims)
                                                           (on failure: tool_result error to the model, up to 2 more calls)
  ◄──────────────────────────────── {kind:"answer", assistant, sig, answer, verification:{ok, issues, retries}, model}
```

* **The model plans, the engine computes.** The model never computes a number: the system prompt (generated from
  `docs/ask/catalog.js`) tells it what exists, and `final_answer` is checked by `verify.js`.
* **No state.** The client carries the transcript. Every assistant turn the worker returns is signed (HMAC-SHA256,
  `sign.js`) and must come back unchanged; a forged or edited turn is a `400 {error:"bad transcript"}`.
* **Claims pair every figure with its place.** `final_answer.claims` lists each figure as `{place, field, value, call}`; the
  verifier checks each claim against its call's result and every number of the answer against the claims of the place it is
  written next to, so a correct number next to the wrong place is caught (ASK_CONTRACT §6 rule 6).
* **Standard methods.** For the site's core questions the model calls `method {id, params}` (docs/ask/methods.js): a named rule the
  site owner can review, run by the engine exactly as written; the card labels such answers (ASK_CONTRACT §12).
* **No data reads.** The worker never fetches the data files; it only talks to the model. The catalog (field names, enumerations,
  definitions, layers, vintages) is the one thing it shares with the engine.

### Files

| File | Role |
|---|---|
| `src/index.js` | HTTP: CORS, `/health`, `POST /ask`, `POST /feedback`, rate limits, error → status mapping, the model call (`makeCallModel`), one log line per request |
| `src/loop.js` | `step(body, env, callModel)`: validation (§3), signature checks, messages, the model call, verification retries, signing |
| `src/prompt.js` | `systemPrompt(catalog)` and `toolDefinitions(catalog)` (the 9 tools' JSON schemas, the method list and the CLAIMS rules); `node worker/src/prompt.js --print` prints the prompt and its size |
| `src/verify.js` | `verify(answer, {question, turns})` → `{ok, issues}` (ASK_CONTRACT §6 rules 1–6) |
| `src/claims.js` | rule 6: each claim against its call's result, then each number of the answer against the claims of its place |
| `src/sign.js` | `sign(blocks, secret)`, `verifySig(blocks, sig, secret)`, `secretFor(env)` (Web Crypto; canonical JSON with sorted keys) |
| `tests/loop.test.js` | the offline suite (scripted fake model; the real engine for one end-to-end case when `docs/ask/engine.js` is present) |
| `tests/claims.test.js` | rule 6 against real engine results: 40 realistic correct answers must pass, 16 wrong attributions must fail |
| `tests/methods.test.js`, `tests/methods_doc.js` | every standard method against the equivalent free-tool calls; the review sheet `docs/ask/METHODS_REVIEW.md` |
| `tests/eval.js` | live evaluation through the real model (in-process with `ANTHROPIC_API_KEY`, or `--worker URL` against a deployment) |

Node 22, ES modules, no package.json, no dependencies. `wrangler` bundles `../../docs/ask/catalog.js` and `../../docs/ask/methods.js`
into the worker (deploy-worker.yml redeploys when either changes).

## Protocol (what the client must do)

Request: `{v: 3, q, turns: [{assistant, sig, results:[{tool_use_id, content, is_error}]}], prior: [{q, answer}], client}` —
`q` 3–400 characters, at most 8 turns, at most 3 prior pairs, each result `content` a string of at most 24 KB (truncate with
`"…(truncated)"` before sending). Responses are JSON with `cache-control: no-store`.

* `kind:"tools"`: run every call, append `{assistant, sig, results}` **exactly as returned** (key order is free; values are not),
  post again. Every `tool_use` block needs exactly one result.
* `kind:"answer"`: the loop ends. Show `answer.answer` only when `verification.ok` is true; otherwise show the results
  (table / highlights) with the notice from ASK_CONTRACT §7.
* **`final_answer` alongside other calls.** The model is told to call `final_answer` alone, in its own turn. If it nevertheless
  sends it together with other calls, the worker returns `kind:"tools"` with **all** the calls (and a `note`). The client must
  run the other calls and answer the `final_answer` call with the JSON string `{"ok":true,"note":"call final_answer alone, after
  the other results"}` (`is_error: false`). The model then calls `final_answer` again, alone, and that one is verified.
* **Verification retries happen inside one HTTP step.** A failed `final_answer` is fed back to the model as a `tool_result`
  error ("Verification failed: … rewrite using only numbers from the tool results, or call a tool to get the figure") and the
  model is called again, up to 2 extra times; the response carries the last attempt and `verification.retries`. If the model
  answers a retry by calling tools instead, the step returns `kind:"tools"` for those calls and the failed attempt is dropped
  from the transcript (the client only ever echoes the turn it was given). A step may therefore take up to 3 model calls
  (≈ 120 s worst case); the client waits 120 s per step.
* `step` in a response is the number of the model call that produced it (`turns.length + 1`); `MAX_STEPS` (8) forces the last
  call to `final_answer` with a user message saying so (current models accept only `tool_choice: auto`).
* Errors: `400 {error}` (bad body; `"bad transcript"` for signature/bookkeeping failures; a too-large result), `403` (origin),
  `429 {error, retry_after_s}` (per-visitor minute limit or the daily cap; only requests with `turns.length === 0` count),
  `502 {error, detail}` (model/internal), `504 {error}` (the model took more than 25 s). Error texts are plain sentences.

## Verification (verify.js)

1. Every number in `answer`, `interpretation`, `caveats`, `not_in_data` (and literal `table.rows`) must be in a tool result of
   this question (same digits), or a tool-result value rounded to the written precision (≥ 2 significant digits; `million`,
   `billion`, `thousand`, `k` handled: 11,802,321 may be written 11.8 million, 38.2 as 38, but 38 may not be written 40), or in
   the question, or a definitional constant (`CONSTANTS` in the catalog, plus `100,000`) or a data vintage. Phone numbers,
   `NCT` ids, ordinals (`34th`) and district ids are not figures; district ids must appear in a result or the question. Number
   words above ten are checked the same way; "hundreds / thousands / millions / dozens" are rejected as vague.
2. Every capitalised token in `answer` outside the stoplist (sentence words, the site's vocabulary, all state names and USPS
   codes, every word of the catalog text and of the question) must appear in a tool result (case-insensitive) — no
   re-attributed figures.
3. `map.highlight.ids` / `map.place` must appear in a result; `*.from_call` must be the id of a `query`, `compare`, `profile`
   or `find_places` call of this question; `map.unit` / `layer` / `params` / `state` and `sources` are checked against the catalog.
4. Style: no URLs, markdown or list formatting, first person, advice verbs, eligibility talk (outside a negation) or claims that a
   trial is "available to" someone; `answer` ≤ 1,200 characters; array caps (alternatives 3, not_in_data 4, caveats 5, follow_ups 3).
5. `answerable:"no"` needs a non-empty `not_in_data`. `SCOPE_TEXT` / `OTHER_TEXT` answers skip the number, name and claim checks.
6. Claims (`claims.js`): an answer that writes a figure needs `claims`; each claim must match its call's result (the row with that
   id, or the result itself for whole-result figures such as `count` with the scope as place; a method's sub-call `toolu_….2`); then
   each number of the answer must be a claim value (or its written rounding) of the place named nearest before it in its clause (or
   right after it, "33.1% in Montana"), a clause with no place continuing the last place named, a sentence with no place carrying
   scope figures. The full rule and the claim format for non-row figures are in ASK_CONTRACT §6.

Issues are specific sentences ("number 38.7% in answer is not in any tool result (closest: 38.2); …", "\"18 trials\" is written next to
Cameron County, Texas, but the claims give Cameron County, Texas 9 trials_listed_here and Hidalgo County, Texas 18
trials_listed_here; write each figure next to its own place.") so the model can act on them.

## Feedback (`POST /feedback`)

The answer card asks "Was this right?" (Yes / No) and offers "Report a problem" (a prefilled GitHub issue; no worker involved).
Yes / No post `{v:3, kind:"feedback", q, verdict, answer_text, interpretation, steps, model, data_as_of, verified, method}` to
`<worker origin>/feedback`. The route checks the origin (same `ALLOWED_ORIGINS` and CORS as `/ask`), the size (≤ 20 KB, else 413),
the shape (400) and its own per-visitor limit (`FEEDBACK_PER_MINUTE`, default 6 a minute; 429), writes **one log line**
`{"feedback":{…}}` and returns `{ok:true}`. Nothing about the visitor is logged or stored; the client never waits on it.

Reading the feedback: Cloudflare dashboard → **Workers & Pages → trial-map-ask → Logs** (Workers Logs; `[observability]` is on in
`wrangler.toml`), set the time range, and filter for `feedback` (the search box, or a filter on the message containing `"feedback"`);
each event's message is the JSON line with the question, the verdict, the answer as shown, how it was read and the tool calls. For a
live view: `cd worker && npx wrangler tail --search feedback`. Workers Logs keeps events for a limited time (days, by plan): copy out
anything worth keeping, or open an issue for it.

## Settings (`wrangler.toml`)

- `MODEL` (default `claude-sonnet-5-5`): the one model. `MODEL_FAST` is read and ignored (kept for a later decision; switching
  models between steps would also lose the prompt cache). `MAX_STEPS` (8).
- `ALLOWED_ORIGINS`: the pages allowed to call the worker. `SITE_BASE`: reported by `/health`.
- `PER_MINUTE` (12) per visitor, `DAILY_CAP` (3000) across visitors — best effort, per worker isolate; the spending limit on the
  key is the hard stop. Only the first step of a question counts. `FEEDBACK_PER_MINUTE` (6, optional): feedback posts per visitor.

Secrets (never in the repository or the site):
- `ANTHROPIC_API_KEY` — required.
- `ASK_SIGNING_SECRET` — optional HMAC secret for the transcript signatures. When unset the worker uses the SHA-256 of the API
  key (never returned anywhere); rotating the key then invalidates in-flight questions, which simply restart.

Model calls: `POST https://api.anthropic.com/v1/messages`, `anthropic-version: 2023-06-01`, `max_tokens` 2500, no `temperature`,
`system` and the last tool carry `cache_control: {type:"ephemeral"}` (the ~14k-token prompt is cached across steps and
questions), `tool_choice: {type:"auto"}` (any / tool are rejected by current models; the system prompt requires tool calls), 25 s timeout, one retry after 1.5 s on 429/529/5xx.

Logging: one JSON line per request (question text, step, kind, model, verification ok/issues, retries, tool names, elapsed ms,
token usage). No visitor identifier is logged or stored.

## Deploy

```
cd worker
npx wrangler login                        # or set CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID in the environment
npx wrangler deploy                       # prints the address, e.g. https://trial-map-ask.<account>.workers.dev
npx wrangler secret put ANTHROPIC_API_KEY
npx wrangler secret put ASK_SIGNING_SECRET   # optional
```

`.github/workflows/deploy-worker.yml` does the same on demand and whenever `worker/` changes on `main`: offline suite → deploy →
secrets → `/health` → `node worker/tests/eval.js --worker <url>/ask --max 25` (informational) → sets `ASK_URL` in `docs/site.js`.

## Tests

- `node worker/tests/loop.test.js` — no network: signatures (round-trip, forged turn → 400), result and call caps, forced final
  at `MAX_STEPS`, verification accept/reject cases (rounded and million forms accepted; invented numbers, re-attributed places,
  unknown ids, bad layers/params, markdown, URLs, advice, first person, `answerable:"no"` without `not_in_data` rejected) with
  the internal retry, text-only replies, `SCOPE_TEXT`, prior Q/A rendering, the `final_answer`-alongside-tools rule, HTTP status
  codes, rate limits (step 0; continuation budget), body size, `makeCallModel` (request shape, retry, timeout), prompt sections and tool-schema validity
  (every field path in the prompt exists in the catalog), and — when `docs/ask/engine.js` is present — the canonical Texas
  question end to end through the real engine with a verified answer.
- `node worker/tests/claims.test.js` — rule 6 against real engine results (prints how many realistic correct answers verified).
- `node worker/tests/methods.test.js` — the standard methods; `node worker/tests/methods_doc.js` rewrites `docs/ask/METHODS_REVIEW.md`.
- `node worker/src/prompt.js --print` — the rendered system prompt (review it after a catalog change) and its size.
- `node worker/tests/eval.js [--max N] [--worker URL]` — the live evaluation (see `tests/EVAL.md`). `.github/workflows/ask-eval.yml`
  runs 30 questions on pull requests and pushes to main that touch `docs/api/**`, `docs/ask/**` or `worker/**`, and after each weekly
  refresh (`workflow_run` on "Refresh registry data" / "Refresh cosponsors": their pushes use GITHUB_TOKEN and trigger nothing);
  a failure after a refresh opens or comments on the issue "Ask the map: evaluation failing after data refresh".

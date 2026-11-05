# "Ask the map" helper

A small Cloudflare Worker behind the question box on the map and the homepage. It holds the Anthropic API key (the site's
code never sees it), reads the same published data files as the Data API (`docs/api/*.json` on the live site), and returns
`{route, answer, table, sources, view, data_as_of}`. The site moves the map to `view` and outlines the places in `view.hl`.

How a question is answered:

1. **Plan** (`MODEL_PLAN`, Haiku): the question is turned into a small JSON request: a search (ZIP, cancer type, keyword,
   radius) or a data lookup (level, state, metric, cancer type, order, how many, cosponsor status, a single place), or
   `scope` (patient-specific / medical questions) or `other` (not something the map measures).
2. **Execute** (plain code, no model): the request runs over `api/all_counties.json`, `api/all_districts.json`,
   `api/all_states.json` or `api/national.json`. Ranking, filtering and the numbers in the table come only from those files.
3. **Write** (`MODEL_WRITE`, Sonnet): two or three sentences from the table, with the rule that no figure may appear that
   is not in the table. Search questions get a fixed sentence and open the finder; scope and other questions get fixed text.

The model never computes a number. Every answer lists the files it was read from and the data date.

## Deploy

```
cd worker
npx wrangler login                       # or set CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID in the environment
npx wrangler deploy                      # prints the worker's address, e.g. https://trial-map-ask.<account>.workers.dev
npx wrangler secret put ANTHROPIC_API_KEY
```

Then set `ASK_URL` in `docs/site.js` to `https://trial-map-ask.<account>.workers.dev/ask`. While `ASK_URL` is empty the
question boxes stay hidden and the site works as before. `GET /health` on the worker returns `{ok:true}`.

## Settings (`wrangler.toml`)

- `SITE_BASE`: where the data files are read from. Change it if the site moves to its own domain.
- `ALLOWED_ORIGINS`: the pages allowed to call the worker (the site plus localhost for testing). Add a new domain here.
- `MODEL_PLAN`, `MODEL_WRITE`: the two models. Haiku for planning keeps most questions at a fraction of a cent.
- `PER_MINUTE`: questions per visitor per minute (best effort, per worker instance). `DAILY_CAP`: questions per day in
  total across the site, after which the box answers with a "try tomorrow" message. Both protect the API bill.

Nothing about a visitor is stored. Each question is logged (question text, route, view, first 300 characters of the answer)
in the worker's own logs so wrong answers can be found and fixed.

## Testing

`tests/questions.json` is a set of questions with the route and view they should produce. After a deploy:

```
node tests/run.js https://trial-map-ask.<account>.workers.dev/ask
```

It posts each question, checks the route and the view's query string, and prints every answer for a read-through.
Because the plan step is a model, a question may occasionally be read differently from the expected route; a failure
there means "read it", not necessarily "broken".

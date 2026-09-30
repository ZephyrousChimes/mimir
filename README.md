# nl2sql-arc

A small NL→SQL system built in three stages, each one added *because* the
previous stage's own measured failures demanded it — reproducing, by hand,
on a tiny hand-owned schema, the actual historical arc of the field
(WikiSQL slot-filling → Spider-era schema linking), rather than trying a
grab-bag of common baselines.

**The point of this project is the reasoning chain, not the leaderboard number.**
Every design decision below was predicted *before* the code that tests it
was run, and the prediction is checked against what actually happened.

**Status**: the stage-by-stage evaluation scripts described below (Stage 0/1/2,
the WikiSQL/Spider runners, `metrics.py`) did their job — establishing and
testing the reasoning chain — and have since been removed. What's left, and
what this repo now runs, is Stage 2's engine only, factored into
`src/encoder.py` (NL + schema → a `Grounding`), `src/decoder.py` (`Grounding`
+ foreign keys → SQL, deterministically), and `src/pipeline.py` (glues the
two), served by `src/serve.py` — a small local app: upload any SQLite
database, ask it a question, see the generated SQL and its results. The
sections below are kept as the real record of *why* it's built this way, not
as instructions you can still run verbatim.

## The schema (`data/schema.sql`)

Four tables, hand-designed so two specific, well-known NLIDB failure modes
are reproducible on demand, not stumbled on by luck:

```
department(id, name, budget)      -- one row: name = 'What'  <- value/lexical collision trap
employee(id, name, dept_id, salary)
project(id, name)
assignment(emp_id, project_id, hours)   -- bridge table, never named lexically
                                         -- by any question that only says
                                         -- "employees" / "projects"
```

`employee` and `project` are reachable *only* through `assignment` — no
shortcut FK — so the bridge-table trap is isolated, not confounded with a
second, competing join path (an earlier draft had `project.lead_emp_id` as
a direct FK, which let FK-shortest-path silently pick the wrong edge; a
real, separate problem — see "What this project deliberately does not
solve" below — removed so it doesn't muddy this story).

19 hand-written, hand-verified gold questions in `data/questions.json`,
grouped by exactly what they test: bare listing, equality filter, numeric
comparison, the value-collision trap, a named join, the unnamed-bridge
join, and two deliberately out-of-grammar aggregation questions.

## Stage 0 — naive fine-tuned seq2seq (the null hypothesis)

**Why this and only this as a baseline**: it's the absence of every
mechanism the later stages add — no schema linking, no output-grammar
constraint, no join reasoning. Model: `cssupport/t5-small-awesome-text-to-sql`,
free-text generation, same prompt format as its model card.

**Predicted before running**: free-text generation gives no structural
guarantee of valid SQL, and nothing grounds question words to the *correct*
schema element when a plausible-but-wrong one exists (e.g. inventing an
`employee.department` column instead of the real `employee.dept_id` + a
join) — so the dominant failure should be wrong/hallucinated identifiers,
not syntax.

**Result**: 1/19 (5.3%) execution accuracy. 12 of 18 failures are
`unknown_table_or_column`; only 1 is a syntax error. Concretely, the model
invents a non-existent `employee.department` text column *seven separate
times* across different questions (`SELECT name FROM employee WHERE
department = 'Sales'`) instead of ever producing the real join — exactly
the predicted failure, and the same pattern (schema grounding, not
grammar, is the dominant failure) as this project's own earlier
Spider-scale run in `rosette-spider` found at 1000x the question count.

Full predictions/outputs: `artifacts/stage0_baseline_results.csv`.

## Stage 1 — WikiSQL-style slot-filling

**Why this fix, specifically**: Stage 0's own failure taxonomy motivates
it — stop generating SQL as free text; fill closed-vocabulary slots
(table, SELECT column, one WHERE column/op/value) chosen only from things
that actually exist, making an invalid-syntax or hallucinated-identifier
output structurally impossible.

**Predicted before running**: syntax/grounding errors should drop to
~zero on single-table questions, and every question needing a second
table should fail *categorically* — not "wrong", but inexpressible,
because WikiSQL's grammar has no join at all.

**Result**: 8/19 (42.1%). All 8 single-table questions (A/B/C) pass; all
11 multi-table or aggregation questions (D–G) fail, and every single
failure is `runs_wrong_result` — zero syntax errors, zero hallucinated
identifiers. The failure mode changed exactly as predicted: from "invalid
output" to "valid output, wrong shape."

One extra, unplanned finding here: category D (the value-collision trap)
also fails at this stage, but for a *different* reason than expected —
not a wrong match, but a hard-coded stopword list that excludes "what"
from ever being checked as a value in the first place. That's a cleaner,
more honest illustration of the brittleness than a wrong match would have
been: the standard fix (filter interrogatives before value-matching)
*causes* this exact failure.

Full predictions/outputs: `artifacts/stage1_slotfill_results.csv`.

## Stage 2 — Spider-style: schema linking + FK-graph join compilation

**Why this fix, specifically**: Stage 1's ceiling *is* the join problem.
Add (1) a naive lexical/value schema linker that can select more than one
table, and (2) deterministic join compilation via the schema's own
foreign-key graph (the same "meaning vs. mechanical plumbing" split IRNet
uses — a model, or a heuristic, decides *which* tables matter; a plain
graph search decides *how* to join them).

Two changes from Stage 1 were made deliberately, as a controlled
experiment, each with a stated prediction:

1. **Value-grounding no longer hard-excludes "what"/"which"/"who".**
   Predicted to fix D1/D2 (and E3, a join+collision combo) — because the
   value is now allowed to be checked at all. *Also predicted, honestly, as
   a risk*: since "what" is a real value in this schema, and starts most
   of this question set's phrasing, removing the hard exclusion could
   cause **new** false-positive matches on formerly-correct single-table
   questions that happen to contain the literal word "what".

2. **Unnamed-bridge closing.** Once two tables are linked but not directly
   FK-connected, walk the shortest path between them in the FK graph and
   pull in whatever table sits on it — even though the question never
   names it. Predicted to fix F1–F4.

**Result**: 14/19 (73.7%).

| category | stage 0 | stage 1 | stage 2 |
|---|---|---|---|
| A — no filter (3) | 0/3 | 3/3 | 3/3 |
| B — equality filter (3) | 0/3 | **3/3** | **0/3** |
| C — comparison filter (2) | 1/2 | 2/2 | 2/2 |
| D — value-collision trap (2) | 0/2 | 0/2 | **2/2** |
| E — named join (3) | 0/3 | 0/3 | **3/3** |
| F — unnamed bridge join (4) | 0/4 | 0/4 | **4/4** |
| G — out-of-grammar stretch (2) | 0/2 | 0/2 | 0/2 |

Full per-question crosstab: `artifacts/diff_table.csv`. Per-stage
predictions/outputs: `artifacts/stage2_linked_results.csv`.

**Both predictions for change (1) came true, including the risky one.**
D1/D2/E3 flip from wrong to right, exactly as predicted. But all three of
category B — previously perfect in Stage 1 — now fail, and the reason is
exactly the predicted risk: with "what" no longer excluded, questions like
*"What is Alice's salary?"* now spuriously value-match the literal word
"What" against `department.name = 'What'`, pull `department` into the
query, and add a bogus join + filter that makes the real answer
disappear. **The fix for the deliberate trap has a real, measured blast
radius on unrelated questions that happen to share a word with it.** This
is not a bug I patched away — it's the single most important finding in
the project: it's a live, reproducible demonstration of exactly why the
field replaced hard-coded string/value matching with *learned*,
context-weighted attention (RAT-SQL) instead of a symbolic rule. A rule
either excludes "what" (and misses the trap) or includes it (and creates
collateral damage) — there is no threshold that gets both right, because
the rule has no way to weigh "is this specific occurrence of 'what' likely
a value" against everything else in the sentence. That's precisely the
job description of relation-aware self-attention.

**Bridge-closing (2) fixed all four F questions outright**, with no
observed collateral damage — the FK-path search only ever adds a table
that's actually necessary to connect two already-linked tables, so it
doesn't have the same blast-radius problem as value-relaxation.

## What this project deliberately does not solve

- **G1/G2 (aggregation + GROUP BY)**: out of this stage's grammar on
  purpose. Fails for a clean, nameable, different reason than everything
  above — not a schema-linking problem, a grammar-coverage problem.
- **Join-path ambiguity**: an earlier schema draft had two valid FK paths
  between `employee` and `project` (a direct "lead" FK, and the
  `assignment` bridge), and FK-shortest-path picked the structurally
  shorter one over the semantically correct one. This is a real, separate,
  documented problem in the literature (disambiguating between multiple
  valid join paths needs the question's verb, not just graph structure) —
  removed from this schema so it doesn't conflate with the bridge-table
  lesson, but worth stating as a known next problem, not a hidden gap.
- **RAT-SQL-style learned linking**: not implemented here. The value-B
  regression above is the empirical argument for *why* it would help,
  demonstrated on a case small enough to fully explain, not asserted from
  reading the paper.

## Scaling to real benchmarks: WikiSQL and Spider

The toy schema proves the reasoning chain in a form small enough to fully
own. The natural next question is whether the same code generalizes to
real data it was never tuned against — so Stage 0 and Stage 1 were rerun
on real WikiSQL questions, and Stage 2's engine (factored out into
`src/link_engine.py`, the *same* code, not a reimplementation) was pointed
at both WikiSQL and real Spider databases.

**Why WikiSQL is the natural fit for Stage 0/1, specifically**: WikiSQL is
single-table by construction — exactly Stage 1's own historical scope — so
porting Stage 1 there isn't a stretch, it's the dataset the design was
already modeling. Each question carries its own tiny table (real natural-
language headers like "Foreign nationals in %", not code-style
identifiers), materialized into its own SQLite file so gold and predicted
SQL execute against identical data. Sample: N=100 fixed-seed questions
from the official validation split (this machine has no GPU; WikiSQL's
~8.4k-row split isn't a same-session CPU run, so a stated, reproducible
sample stands in for it, the same tradeoff the Spider run below makes).

| stage | toy schema (N=19) | WikiSQL (N=100) |
|---|---|---|
| 0 — naive fine-tuned seq2seq | 5.3% | 15.0% |
| 1 — WikiSQL slot-filling | 42.1% | 37.0% |
| 2 — schema linking (single-table, no FKs) | — | 38.0% |

Stage 0 on WikiSQL surfaced a real, on-theme finding: 51/99 failures were
syntax errors, almost all from the model correctly following WikiSQL's own
convention of literally naming the table `table` — a reserved SQL
keyword, which is a syntax error unquoted. That's not a reasoning failure;
it's normalized once (`stage0_wikisql.py::_quote_table_keyword`) as a
known dataset quirk, applied identically regardless of what the model
generated. The *remaining* syntax errors (real ones) come from the model
inconsistently quoting real multi-word headers ("First driver(s)",
"Air date") — the same free-text-generation problem as the toy schema,
now sharper because real headers are natural-language phrases, not single
words.

Stage 1 on WikiSQL reproduces the toy schema's headline pattern exactly:
syntax/grounding errors nearly vanish (1 stray error out of 63 failures),
and every failure is "valid SQL, wrong shape" — the same shift from
invalid output to wrong-shaped output the toy schema showed.

**Stage 2 on WikiSQL is close to a no-op relative to Stage 1** (38% vs.
37%) — expected, since a single table with no foreign keys gives the
linking/bridging machinery almost nothing to do. Porting it there still
found three real, unplanned bugs, each fixed and documented in
`link_engine.py`, because none of them could show up on the toy schema's
narrow, hand-designed conditions:

1. **Ambiguous value grounding.** The toy schema's value matching collects
   *every* column a phrase matches; on the toy schema a given value only
   ever lived in one place, so this never mattered. On real data, the same
   value can appear in two semantically different columns of the *same*
   table (e.g. "Ottawa" as both a Visitor and a Home team) — collecting
   both produced a contradictory `AND` instead of one filter. Fixed by
   treating a phrase that matches more than one column as ambiguous and
   dropping it, the same abstain-on-ambiguity rule already used elsewhere
   in this codebase (`extract.py`'s value grounding, referenced in
   `link_engine.py`'s docstring) — not invented for this fix, recognized
   as the same principle.
2. **A hard-coded 2-word cap on value n-grams.** Real values can be three
   words or more ("South Carolina 2"); the toy schema's values never were.
3. **A literal substring bug**: `"count" in question.lower()` matches
   inside the word **"country"**, so any "What country...?" question
   spuriously triggered `COUNT(*)`. The toy schema's own questions never
   happen to contain "count" as a false substring, so this was invisible
   until run against real data. Fixed with a word-boundary check.

None of these three bugs are about schema linking or joins — the intended
lesson for this stage — they're generalization bugs that only exist
because real data doesn't respect the toy schema's implicit simplifying
assumptions (one value per column, short values, no coincidental
substrings). That's itself worth stating plainly: *porting to new data
surfaces bugs in the harness, not just in the algorithm being tested.*

**Stage 2 on Spider** (N=100 dev questions, fixed seed, real cross-domain
multi-table databases, the identical `link_engine.generate()` unmodified):
**5.0%** — a large, honest drop from the toy schema's 73.7%, and it
breaks down cleanly into two separate causes, not one blur:

- **42 of 95 failures need GROUP BY / ORDER BY / HAVING / LIMIT** in the
  gold query — categorically out of this stage's grammar, the same known
  boundary as the toy schema's category G, just far more common in
  Spider's actual question style than in 19 hand-written questions.
- **53 of 95 fail despite the gold query being in-grammar** (SELECT +
  WHERE + JOIN only) — accuracy restricted to just this in-grammar subset
  is 5/58 (8.6%). The dominant real cause, visible directly in
  `artifacts/stage2_spider_results.csv`: on Spider's larger, more densely
  foreign-key-connected schemas, `_bridge_close` sometimes pulls in far
  more tables than a question needs, and the SELECT-target heuristic
  (tuned against a 4-table schema) picks the wrong column once 3+ tables
  are linked. This is exactly the failure mode `rosette-spider`'s own
  `schema_link.py` docstring predicted but never triggered on this
  project's small schema: *"every table is FK-connected to every other
  ... cascaded through the entire connected component."

Nothing here was patched to inflate the number — the taxonomy above is
what `artifacts/stage2_spider_results.csv` actually shows, and the honest
conclusion is that a lexical/value linker tuned by hand against a 4-table
schema partially transfers (better than the fine-tuned baseline's
Spider-scale 10.1% on syntax-*valid* questions specifically, comparable
in spirit to `rosette-spider`'s own finding that a heuristic linker gives
a "modest" gain), but does not remotely generalize as-is to Spider's real
complexity — which is precisely why RAT-SQL's learned, relation-aware
attention exists instead of a hand-tuned lexical rule at any of these
scales.

The evaluation CSVs these findings are drawn from (`stage0_*`, `stage1_*`,
`stage2_*`, `diff_table_*`) were generated by scripts that have since been
retired — the numbers above are the permanent record of what they found.

## Architecture, as it exists now

```
src/encoder.py   -- NL question + schema names/columns/values -> Grounding
src/decoder.py   -- Grounding + foreign keys -> SQL string, deterministically
src/pipeline.py  -- ground(), then build(). four lines.
src/db_utils.py  -- generic SQLite introspection (schema, FKs, value lookups)
                    for an arbitrary uploaded database, not just one fixed DB
src/serve.py     -- FastAPI app: upload a .db, ask it a question, see the SQL
src/static/      -- the one-page frontend
```

`Grounding` is the formal contract between the two halves: `tables`,
`target`, `filters`, `aggregation` — nothing else crosses that boundary,
and in particular the raw question never reaches `decoder.py`. See the
Stage 2 section above for why each piece of `encoder.py`/`decoder.py`
exists; the code is that same design, just no longer named "Stage 2."

Also present, standalone and not wired into `pipeline.py`: `enc_ngram.py`,
`enc_bm25.py`, `enc_embed.py` — three alternative ways to score which
tables a question refers to (raw n-gram overlap, BM25, sentence-embedding
cosine similarity), kept as separate experiments for comparing against the
current encoder's exact/stem-match approach.

## Running it

```
cd src
uvicorn serve:app --reload
```

Open `localhost:8000`, drop in a SQLite file (`data/arc.db` — the toy
schema this README's findings are about — or any `.sqlite` under
`data/spider/database/*/` from the earlier benchmark runs), and ask it a
question in plain English.

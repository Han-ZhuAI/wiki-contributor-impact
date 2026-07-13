# 16-Day Development Schedule

Project: **Wiki Contributor Impact Model**
Start: **2026-07-13** · End: **2026-07-28**

The plan is deliberately incremental so the git history shows genuine stepwise
development (one or more commits per day). Each day lists a goal, concrete
deliverables, and the commit(s) that should land.

## Phase 1 — Foundations & data acquisition (Days 1–4)

| Day | Date | Goal | Deliverables | Commit(s) |
|----|------|------|--------------|-----------|
| 1 | Jul 13 | Project setup | Repo, README (problem + model design), SCHEDULE, requirements, `.gitignore`, LICENSE, package skeleton, smoke test | `Initial project scaffold` |
| 2 | Jul 14 | MediaWiki API client | `api.py`: fetch revision history for an article, handle `rvcontinue` pagination, polite User-Agent + rate limiting | `Add MediaWiki revision-history client` |
| 3 | Jul 15 | Data models & caching | `dataclasses` for `Revision`; on-disk cache (JSON/parquet) so the API is hit once; fetch Talk-page history too | `Cache raw revisions and add data model` |
| 4 | Jul 16 | Diffing engine | Word-level diff between consecutive revisions; per-revision added/removed token lists; unit tests | `Add revision diff engine + tests` |

## Phase 2 — Core metrics (Days 5–9)

| Day | Date | Goal | Deliverables | Commit(s) |
|----|------|------|--------------|-----------|
| 5 | Jul 17 | Volume metrics | Gross/net words & bytes added per contributor; edit counts; per-user aggregation table | `Compute per-contributor volume metrics` |
| 6 | Jul 18 | Additive vs. maintenance v1 | Heuristic classifier: size delta + comment keywords (`rv`, `revert`, `typo`, `fmt`, `ce`) + minor flag | `Classify edits: additive vs maintenance` |
| 7 | Jul 19 | Classifier hardening | Revert detection via content hashing (identical-to-prior revision); section-addition detection; validate on a labelled sample | `Improve edit classification + revert detection` |
| 8 | Jul 20 | Persistence metric | Token-survival across N later revisions (simplified WikiWho); attribute surviving text to original author | `Add content-persistence (survival) metric` |
| 9 | Jul 21 | Discussion impact | Parse Talk namespace: threads started, replies, signatures; link talk activity to article edits | `Add Talk-page discussion-impact metric` |

## Phase 3 — Composite model & interface (Days 10–12)

| Day | Date | Goal | Deliverables | Commit(s) |
|----|------|------|--------------|-----------|
| 10 | Jul 22 | Contributor profile | Assemble per-user feature vector across all dimensions; normalisation | `Build per-contributor feature profiles` |
| 11 | Jul 23 | Impact scoring | Configurable weighted composite score; contributor ranking; rationale/explanation | `Add configurable composite impact score` |
| 12 | Jul 24 | CLI end-to-end | `python -m wikicontrib analyze <article>` → metrics table + JSON export | `Wire end-to-end CLI` |

## Phase 4 — Evaluation, presentation & delivery (Days 13–16)

| Day | Date | Goal | Deliverables | Commit(s) |
|----|------|------|--------------|-----------|
| 13 | Jul 25 | Visualisation | Radar per contributor, additive-vs-maintenance stacked bars, edit timeline, leaderboard | `Add visualisations` |
| 14 | Jul 26 | Evaluation | Run on 2–3 real articles; weight sensitivity analysis; sanity checks vs known editors | `Evaluate model on real articles` |
| 15 | Jul 27 | Docs & CI | Finalise README/docstrings/usage; polish tests; GitHub Actions CI running pytest | `Add CI and finalise documentation` |
| 16 | Jul 28 | Report & release | Short report (design + results) in `report/`; record demo video; tag `v1.0` | `Write report and tag v1.0` |

## Notes

- **Buffer:** Days 7, 14 double as catch-up days if earlier work slips.
- **Commit discipline:** commit at every working checkpoint, not just once per
  day — the assignment is graded partly on evidence of ongoing effort.
- **Deliverables for submission:** GitHub repo (code + commit history) and a
  short report or video explaining the system's operation.

# WikiContrib Final Report

Version 1.0 - Explainable Wikipedia Contributor-Impact Analysis

Author: Han Zhu (Han-ZhuAI)

## Executive summary

Raw edit counts reward activity rather than durable or collaborative impact. WikiContrib creates an auditable evidence chain from public MediaWiki revisions to four independent contributor axes: volume, additive work, persistence and discussion influence. It preserves raw metrics, normalised features, policy weights and weighted terms so every rank can be reproduced and explained.

Core analytics, evaluation, tests, CI, JSON export, visual summaries and written documentation are complete. This written report is the selected submission explanation; a demo video is intentionally outside this delivery.

The validation baseline is 245 passing tests, 95.45% total coverage and passing Python 3.10 and 3.12 CI jobs. The committed evaluation uses the earliest 50 article and Talk revisions for Alan Turing, Kimchi and Python (programming language).

## 1. Problem and design goals

Wikipedia contributors perform different roles. A high edit count may reflect repeated small corrections, automated transformations or reversions, while a low-count contributor may supply durable prose or resolve a disputed design on the Talk page. A useful impact model must separate evidence types and avoid treating one proxy as ground truth.

WikiContrib addresses five common measurement failures:

- Edit count rewards save frequency and automation, so the model keeps volume, role, persistence and discussion as separate axes.
- Bytes added cannot show whether text survives, so word-token provenance is chained to the final analysed revision.
- Current text hides maintenance and reverted work, so revision-level diff and edit classification remain auditable.
- Talk post count treats every post as equal, so the system constructs a directed reply graph and computes PageRank.
- A single score conceals value judgements, so the output exposes axes, weights, weighted terms and sensitivity results.

The deterministic pipeline is: article and Talk histories -> token diff and provenance -> wikitext element classification -> Talk reply graph -> four-axis contributor profiles -> ranking, JSON and charts.

## 2. Method

### Token-level diff and provenance

Consecutive revisions are tokenised into Unicode word tokens and symbols. The diff records additions and removals, gross words, net words and churn. Provenance chaining assigns each surviving word token to its original contributor. Complete reverts and partial restorations reuse earlier ownership rather than assigning restored text to the restoring editor.

### Four-axis profile and score

For contributor `u`:

- `volume = log(1 + gross_words_u) / log(1 + max_gross_words)`
- `additive = additive_edits_u / article_edits_u`
- `persistence = log(1 + surviving_words_u) / log(1 + max_surviving_words)`
- `discussion = pagerank_u / max_pagerank`

The composite score is the sum of each axis multiplied by its normalised policy weight. The default is 0.25 per axis. Any finite non-negative scale is accepted and renormalised to one. Equal totals use username order as a deterministic tie-break.

### Wikitext element classification

Every changed word is assigned to exactly one of seven locations: prose, heading, reference, template, table, category or link. Fixed precedence prevents nested markup from double-counting. Comments and markup punctuation do not contribute words. These semantic deltas are reporting evidence rather than hidden score multipliers.

### Talk reply graph

Signed and indented Talk posts are grouped by thread. A directed edge runs from the replier to the contributor being answered. Repeated replies increase edge weight; PageRank uses damping 0.85. Same-user article edits within 14 days after a Talk post are temporal associations, not proof that discussion caused the edit.

The safe CLI default analyses the earliest 500 revisions and sets `historical_slice=true`. Full-history persistence requires `--all-revisions`.

## 3. Cross-article evaluation

All cases use the earliest 50 article revisions and earliest 50 Talk revisions. They are historical slices, not current-article rankings.

| Article | Contributors | Balanced winner | Filtered winner | Worst top-10 overlap | Minimum Spearman rho |
|---|---:|---|---|---:|---:|
| Alan Turing | 47 | Conversion script | Raul654 | 0.800 | 0.951 |
| Kimchi | 41 | Kokiri | Kokiri | 0.900 | 0.941 |
| Python (programming language) | 29 | Fubar Obfusco | Fubar Obfusco | 0.800 | 0.941 |

Balanced ranking was compared with volume-, additive-, persistence- and discussion-emphasis policies. The alternatives assign 0.40 to one axis and 0.20 to each remaining axis. Worst top-10 overlap remained between 0.80 and 0.90; minimum Spearman rho remained between 0.941 and 0.951. The largest observed rank shift was 11 positions.

Sensitivity measures ranking stability, not objective accuracy.

## 4. Alan Turing case study

The balanced all-account policy ranks Conversion script first with 0.750. The detector records high-confidence automation indicators for Conversion script and The Anomebot. Under the opt-in human-contributor comparison, Raul654 becomes the balanced winner with 0.728. Volume and persistence emphasis select Manning Bartlett after filtering, while discussion emphasis selects Raul654 before and after filtering.

Automation handling remains auditable:

- Username bot/script markers form the high-confidence tier; comment-only evidence remains review-only.
- Candidate records retain confidence, reason codes and evidence revision IDs.
- Filtering changes only final ranking eligibility. It never deletes revisions or changes token provenance.
- The heuristic is not proof of bot status and requires manual verification before identity claims.

## 5. Validation

The repository baseline contains 245 passing tests and 95.45% total coverage. GitHub Actions validates Python 3.10 and 3.12, runs Ruff, compiles source and tests, executes pytest and rejects coverage below 95%. Regression tests cover exact reverts, partial restoration ownership, scoring, ranking and reply-graph behaviour.

The real-article benchmark contains Alan Turing, Kimchi and Python (programming language). Committed JSON and Markdown preserve the revision cap, historical-slice flag, policy weights, winners, top-k overlap, Spearman correlation and rank shifts.

## 6. Limitations and ethics

- Revision caps can omit later article states and current contributors; capped results must retain their scope warning.
- Token survival measures textual retention, not factual correctness, originality or reader value.
- Wikitext heuristics cannot resolve every malformed or deeply nested construct.
- Talk signatures, indentation and 14-day temporal links are incomplete collaboration proxies.
- PageRank measures graph centrality under a chosen direction and damping value, not authority or consensus quality.

WikiContrib analyses public histories, but public availability does not remove the need for careful interpretation. Rankings should be presented as model outputs under an explicit policy, never as definitive judgements of people. Anonymous and hidden contributors remain source identifiers; the system does not attempt deanonymisation. Automation indicators remain review candidates rather than labels of intent or identity.

## Reproduction

```bash
pip install -e ".[dev]"
ruff check src tests
python -m compileall -q src tests
pytest -q --cov=wikicontrib --cov-report=term-missing --cov-fail-under=95
```

```bash
python -m wikicontrib evaluate "Alan Turing" "Kimchi" \
  "Python (programming language)" --max-revisions 50 \
  --output-json report/evaluation.json \
  --output-markdown report/evaluation.md
```

## Conclusion

WikiContrib meets the intended v1.0 goal: a reproducible, explainable and auditable model that separates content creation, maintenance, survival and discussion influence. Its contribution is not a universal ranking, but a transparent evidence pipeline in which scope, assumptions and value choices remain inspectable.

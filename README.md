# Wiki Contributor Impact Model

[![CI](https://github.com/Han-ZhuAI/wiki-contributor-impact/actions/workflows/ci.yml/badge.svg)](https://github.com/Han-ZhuAI/wiki-contributor-impact/actions/workflows/ci.yml)

A **data-driven computational model** for assessing the impact of individual
contributors on the collaborative formation of a Wikipedia entry.

The model reads the raw **edit history** available from the Wikipedia / MediaWiki
platform and produces per-contributor metrics that differentiate editors along
several independent dimensions rather than by a single naive edit count.

## Problem

On Wikipedia, an article is written collaboratively by many contributors whose
roles differ enormously: some write large amounts of new prose, some revert
vandalism, some copy-edit and format, and some drive consensus on the *Talk*
page without ever changing the article body. A fair model of "impact" must
separate these behaviours instead of rewarding whoever clicked *Save* most often.

## What the model measures

| Dimension | Question it answers | Primary signal |
|-----------|--------------------|----------------|
| **Volume** | How much text did the contributor add? | Net & gross words/bytes added per revision |
| **Additive vs. maintenance** | Did they *create* content or *maintain* it? | Size delta, revert detection, edit-comment keywords, minor flag |
| **Persistence / survival** | Did their text *stay* in the article? | Token survival across later revisions |
| **Discussion impact** | Did they shape the *decisions*? | Signed Talk posts, threads started, weighted reply-graph PageRank, and subsequent article edits |

These feed a configurable **composite impact score** and a per-contributor
profile (a radar of the dimensions above) so contributors can be ranked and
compared transparently.

## Data source

All data comes from the public **MediaWiki Action API** (`prop=revisions`),
which exposes the full revision history of any article and its Talk page,
including revision id, timestamp, user, edit comment, byte size, minor flag and
full wikitext content. No scraping and no credentials are required.

## Status

Under active development. The data pipeline, revision diffing, contributor
volume, additive/maintenance classification, exact-revert detection and
content-persistence metrics are implemented. Talk-page signatures, threads,
replies, discussion centrality and post-to-edit temporal links are also
measured. These signals are assembled into normalised per-contributor feature
profiles and an explainable, configurable weighted composite score. The CLI
also classifies changed words as prose, headings, references, templates,
tables, categories, or links. It exports complete JSON reports and reproducible
PNG visual summaries. See
[SCHEDULE.md](SCHEDULE.md).

Every push and pull request is checked on Python 3.10 and 3.12. The CI workflow
runs static checks, compiles the package and tests, executes the full test suite,
and rejects coverage below 95%.

Reproduce the same checks locally with:

```bash
pip install -e ".[dev]"
ruff check src tests
python -m compileall -q src tests
pytest -q --cov=wikicontrib --cov-report=term-missing --cov-fail-under=95
```

## Quick start

```bash
pip install -e .
python -m wikicontrib analyze "Alan Turing" --with-diff --output-json results/alan-turing.json
```

The safe default analyzes the earliest 500 revisions and labels the result as a
historical slice. To measure persistence against the current article, request
the complete history explicitly:

```bash
python -m wikicontrib analyze "Alan Turing" --all-revisions --with-diff
```

Complete histories can be slow and large for heavily edited articles.

With `--with-diff`, the CLI prints separate volume, persistence, and discussion
leaderboards followed by the four-axis composite ranking. Discussion centrality uses a weighted reply graph: an edge points
from the replying user to the person whose comment they answered. The `linked`
column counts same-user article edits within 14 days after a Talk post. This is
reported as a temporal association rather than a claim that the post caused the
edit.

`--output-json PATH` (or `--json PATH`) writes the complete, ranked analysis and
automatically enables revision-text processing. The export includes article
scope metadata, normalised weights, raw contributor metrics, the four-axis
feature vector, every weighted contribution, and the human-readable score
explanation. Configure the ranking policy explicitly when needed:

```bash
python -m wikicontrib analyze "Alan Turing" --max-revisions 500 \
  --weight-volume 1 --weight-additive 1 \
  --weight-persistence 2 --weight-discussion 1 \
  --output-json results/alan-turing.json
```

Weights accept any finite non-negative scale and are normalised to sum to one.
Use `--top N` to change the number of terminal rows; JSON always retains every
contributor.

Generate the complete visual summary with `--charts-dir`:

```bash
python -m wikicontrib analyze "Alan Turing" --max-revisions 500 \
  --output-json results/alan-turing.json \
  --charts-dir results/alan-turing-figures
```

The chart directory contains a stacked composite-impact leaderboard, an
additive-versus-maintenance role chart, a monthly edit timeline, and radar
profiles for the top five contributors. Every composite bar is split into its
four weighted dimensions so the visual ranking remains explainable.

## Wikitext element classification

Revision text is segmented into seven mutually exclusive semantic locations:
`prose`, `heading`, `reference`, `template`, `table`, `category`, and `link`.
The CLI reports added, removed, and net word-token deltas for each element, and
the JSON export preserves both article-wide and per-contributor breakdowns.
Nested constructs use a fixed precedence to avoid double-counting—for example,
a link inside a reference remains reference content. HTML comments and markup
punctuation do not contribute words.

## Contributor feature profiles

`wikicontrib.profile.build_profiles` joins article and Talk metrics for every
observed contributor, including article-only and Talk-only participants. It
preserves the raw evidence and adds four comparable `0..1` axes:

| Axis | Normalised signal |
|------|-------------------|
| `volume` | Log-scaled gross words touched, relative to the article maximum |
| `additive` | Share of the contributor's article edits classified as additive |
| `persistence` | Log-scaled surviving words, relative to the article maximum |
| `discussion` | Reply-graph PageRank, relative to the article maximum |

Counts use log scaling so one extreme editor does not visually flatten every
other profile.

## Composite impact scoring

`wikicontrib.scoring.score_profiles` ranks the feature profiles with a weighted
sum. The deliberately neutral default gives each axis a weight of `0.25`;
callers can pass `ScoreWeights` to express a different research policy. Any
non-negative scale is accepted and normalised to sum to one:

```python
from wikicontrib.scoring import ScoreWeights, score_profiles

weights = ScoreWeights(volume=1, additive=1, persistence=2, discussion=1)
impact = score_profiles(profiles, weights)
print(impact.ranked[0].explanation)
```

The model reports the vector as well as the scalar. Each ranked result retains
all four axis values, the normalised weights, every weighted term, and a short
calculation explanation. Equal totals use username order as a deterministic
tie-break; changing the weights can therefore change the rank, but never hides
why it changed.

## Cross-article evaluation

Use `evaluate` to compare the balanced ranking with volume-, additive-,
persistence-, and discussion-emphasis policies across multiple real articles:

```bash
python -m wikicontrib evaluate "Alan Turing" "Kimchi" \
  "Python (programming language)" --max-revisions 50 \
  --output-json report/evaluation.json \
  --output-markdown report/evaluation.md
```

The evaluation reports winner changes, top-k overlap, Spearman rank
correlation, mean absolute rank shift, and maximum rank shift. These are
sensitivity diagnostics rather than ground-truth accuracy claims; capped runs
remain explicitly described as historical slices. It reports both the original
winner and the winner after high-confidence automated-account candidates are
omitted from ranking eligibility.

## Automation-aware rankings

Automation handling is deliberately auditable. Bot/script markers in a username
form the high-confidence tier; edit-comment evidence alone remains review-only
because a human editor may simply mention a bot. Candidate records include the
reason codes and evidence revision IDs.

By default, `analyze` still ranks every observed account. Request the comparison
policy explicitly when the research question concerns human contributors:

```bash
python -m wikicontrib analyze "Alan Turing" --max-revisions 50 \
  --exclude-automated-candidates --output-json results/alan-turing-human.json
```

This option changes only eligibility for the final composite ranking. Every
revision remains in the token diff and provenance chain, so later contributions
are evaluated against the article state that editors actually encountered. The
heuristic is not proof of bot status, and its candidates still require manual
verification before making claims about a named editor.

## Repository layout

```
src/wikicontrib/    # the model package
tests/              # unit tests
data/               # cached raw revision data (git-ignored)
report/             # written report and figures
SCHEDULE.md         # 16-day development plan
```

## License

MIT — see [LICENSE](LICENSE).

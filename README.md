# Wiki Contributor Impact Model

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
measured. Contributor profiles and the composite model remain planned; see
[SCHEDULE.md](SCHEDULE.md).

## Quick start

```bash
pip install -e .
python -m wikicontrib analyze "Alan Turing" --with-diff
```

The safe default analyzes the earliest 500 revisions and labels the result as a
historical slice. To measure persistence against the current article, request
the complete history explicitly:

```bash
python -m wikicontrib analyze "Alan Turing" --all-revisions --with-diff
```

Complete histories can be slow and large for heavily edited articles.

With `--with-diff`, the CLI prints separate volume, persistence, and discussion
leaderboards. Discussion centrality uses a weighted reply graph: an edge points
from the replying user to the person whose comment they answered. The `linked`
column counts same-user article edits within 14 days after a Talk post. This is
reported as a temporal association rather than a claim that the post caused the
edit.

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

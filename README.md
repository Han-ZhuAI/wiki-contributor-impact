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
| **Discussion impact** | Did they shape the *decisions*? | Talk-namespace participation: threads started, replies, activity linked to article edits |

These feed a configurable **composite impact score** and a per-contributor
profile (a radar of the dimensions above) so contributors can be ranked and
compared transparently.

## Data source

All data comes from the public **MediaWiki Action API** (`prop=revisions`),
which exposes the full revision history of any article and its Talk page,
including revision id, timestamp, user, edit comment, byte size, minor flag and
full wikitext content. No scraping and no credentials are required.

## Status

Under active development — see [SCHEDULE.md](SCHEDULE.md) for the 16-day plan and
the git history for stepwise progress.

## Quick start (target interface)

```bash
pip install -r requirements.txt
python -m wikicontrib analyze "Alan Turing" --max-revisions 500
```

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

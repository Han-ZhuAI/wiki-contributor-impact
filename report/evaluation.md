# Composite-score sensitivity evaluation

Scope: the earliest 50 revisions per article. The balanced baseline uses equal weights; each alternative doubles one axis, producing normalised weights of 0.4/0.2/0.2/0.2.

## Alan Turing

Revisions: 50; Talk revisions: 50; contributors: 47; balanced winner: **Conversion script**.

| Policy | Winner | Top-k overlap | Spearman ρ | Mean shift | Max shift |
|---|---|---:|---:|---:|---:|
| balanced | Conversion script | 1.000 | 1.000 | 0.00 | 0 |
| volume_emphasis | Conversion script | 0.800 | 0.983 | 1.74 | 6 |
| additive_emphasis | Conversion script | 1.000 | 1.000 | 0.00 | 0 |
| persistence_emphasis | Conversion script | 0.900 | 0.992 | 0.98 | 6 |
| discussion_emphasis | Raul654 | 0.800 | 0.951 | 2.72 | 11 |

Distinct winners: Conversion script, Raul654. Worst top-10 overlap: 0.800; lowest Spearman ρ: 0.951.

Automated-account heuristic candidates: Conversion script, The Anomebot.
**Face-validity warning:** the balanced winner matches the automation heuristic; do not interpret this as human impact until the account and import history are reviewed.

## Kimchi

Revisions: 50; Talk revisions: 50; contributors: 41; balanced winner: **Kokiri**.

| Policy | Winner | Top-k overlap | Spearman ρ | Mean shift | Max shift |
|---|---|---:|---:|---:|---:|
| balanced | Kokiri | 1.000 | 1.000 | 0.00 | 0 |
| volume_emphasis | Kokiri | 0.900 | 0.950 | 2.54 | 11 |
| additive_emphasis | Kokiri | 1.000 | 1.000 | 0.00 | 0 |
| persistence_emphasis | Kokiri | 0.900 | 0.976 | 1.71 | 6 |
| discussion_emphasis | Kokiri | 0.900 | 0.941 | 3.02 | 11 |

Distinct winners: Kokiri. Worst top-10 overlap: 0.900; lowest Spearman ρ: 0.941.

Automated-account heuristic candidates: none.

## Python (programming language)

Revisions: 50; Talk revisions: 50; contributors: 29; balanced winner: **Fubar Obfusco**.

| Policy | Winner | Top-k overlap | Spearman ρ | Mean shift | Max shift |
|---|---|---:|---:|---:|---:|
| balanced | Fubar Obfusco | 1.000 | 1.000 | 0.00 | 0 |
| volume_emphasis | Fubar Obfusco | 0.900 | 0.941 | 1.72 | 8 |
| additive_emphasis | Fubar Obfusco | 1.000 | 1.000 | 0.00 | 0 |
| persistence_emphasis | Fubar Obfusco | 0.900 | 0.941 | 1.72 | 8 |
| discussion_emphasis | Fubar Obfusco | 0.800 | 0.965 | 1.52 | 7 |

Distinct winners: Fubar Obfusco. Worst top-10 overlap: 0.800; lowest Spearman ρ: 0.941.

Automated-account heuristic candidates: Conversion script.

## Interpretation limits

- Weight sensitivity measures ranking stability, not whether a ranking is objectively correct.
- Capped runs describe historical slices and must not be presented as current-article results.
- Talk signatures and temporal post-to-edit links are incomplete proxies, not causal evidence.
- Face-validity findings should be checked against editor histories before drawing conclusions.

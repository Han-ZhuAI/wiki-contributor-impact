# Composite-score sensitivity evaluation

Scope: the earliest 50 revisions per article. The balanced baseline uses equal weights; each alternative doubles one axis, producing normalised weights of 0.4/0.2/0.2/0.2.

## Alan Turing

Revisions: 50; Talk revisions: 50; contributors: 47; balanced winner: **Conversion script**.

| Policy | All-account winner | Filtered winner | Top-k overlap | Spearman ρ | Mean shift | Max shift |
|---|---|---|---:|---:|---:|---:|
| balanced | Conversion script | Raul654 | 1.000 | 1.000 | 0.00 | 0 |
| volume_emphasis | Conversion script | Manning Bartlett | 0.800 | 0.983 | 1.74 | 6 |
| additive_emphasis | Conversion script | Raul654 | 1.000 | 1.000 | 0.00 | 0 |
| persistence_emphasis | Conversion script | Manning Bartlett | 0.900 | 0.992 | 0.98 | 6 |
| discussion_emphasis | Raul654 | Raul654 | 0.800 | 0.951 | 2.72 | 11 |

Distinct winners: Conversion script, Raul654. Worst top-10 overlap: 0.800; lowest Spearman ρ: 0.951.

Automated-account review candidates: Conversion script, The Anomebot.
High-confidence ranking exclusions: Conversion script, The Anomebot.
- Conversion script: confidence=high; signals=explicit_automation_comment, username_script_marker; evidence revisions=7471, 7520
- The Anomebot: confidence=high; signals=username_bot_marker; evidence revisions=1456491
**Ranking comparison:** the balanced all-account winner is a high-confidence automation candidate; the filtered winner is **Raul654**.

## Kimchi

Revisions: 50; Talk revisions: 50; contributors: 41; balanced winner: **Kokiri**.

| Policy | All-account winner | Filtered winner | Top-k overlap | Spearman ρ | Mean shift | Max shift |
|---|---|---|---:|---:|---:|---:|
| balanced | Kokiri | Kokiri | 1.000 | 1.000 | 0.00 | 0 |
| volume_emphasis | Kokiri | Kokiri | 0.900 | 0.950 | 2.54 | 11 |
| additive_emphasis | Kokiri | Kokiri | 1.000 | 1.000 | 0.00 | 0 |
| persistence_emphasis | Kokiri | Kokiri | 0.900 | 0.976 | 1.71 | 6 |
| discussion_emphasis | Kokiri | Kokiri | 0.900 | 0.941 | 3.02 | 11 |

Distinct winners: Kokiri. Worst top-10 overlap: 0.900; lowest Spearman ρ: 0.941.

Automated-account review candidates: Template namespace initialisation script.
High-confidence ranking exclusions: Template namespace initialisation script.
- Template namespace initialisation script: confidence=high; signals=username_script_marker; evidence revisions=10163674

## Python (programming language)

Revisions: 50; Talk revisions: 50; contributors: 29; balanced winner: **Fubar Obfusco**.

| Policy | All-account winner | Filtered winner | Top-k overlap | Spearman ρ | Mean shift | Max shift |
|---|---|---|---:|---:|---:|---:|
| balanced | Fubar Obfusco | Fubar Obfusco | 1.000 | 1.000 | 0.00 | 0 |
| volume_emphasis | Fubar Obfusco | Fubar Obfusco | 0.900 | 0.941 | 1.72 | 8 |
| additive_emphasis | Fubar Obfusco | Fubar Obfusco | 1.000 | 1.000 | 0.00 | 0 |
| persistence_emphasis | Fubar Obfusco | Fubar Obfusco | 0.900 | 0.941 | 1.72 | 8 |
| discussion_emphasis | Fubar Obfusco | Fubar Obfusco | 0.800 | 0.965 | 1.52 | 7 |

Distinct winners: Fubar Obfusco. Worst top-10 overlap: 0.800; lowest Spearman ρ: 0.941.

Automated-account review candidates: Conversion script.
High-confidence ranking exclusions: Conversion script.
- Conversion script: confidence=high; signals=explicit_automation_comment, username_script_marker; evidence revisions=3492, 110220

## Interpretation limits

- Weight sensitivity measures ranking stability, not whether a ranking is objectively correct.
- Capped runs describe historical slices and must not be presented as current-article results.
- Talk signatures and temporal post-to-edit links are incomplete proxies, not causal evidence.
- Face-validity findings should be checked against editor histories before drawing conclusions.
- Automation filtering changes only ranking eligibility; it never deletes revisions or rewrites provenance.

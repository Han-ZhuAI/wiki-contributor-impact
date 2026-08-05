"""Publication-ready visual summaries for contributor-impact analysis.

The plots keep the model's dimensions visible instead of presenting the
composite score as a black box.  All functions use Matplotlib's headless Agg
backend and write deterministic PNG files, so they work in CI and from the CLI
without a desktop session.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from math import pi
from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir

from .api import RawRevision
from .classify import EditType, classify_edit
from .diff import diff_history
from .profile import ProfileReport
from .reverts import find_identity_reverts
from .scoring import DIMENSIONS, ContributorImpact, ImpactReport


def _load_pyplot():
    """Configure a writable cache and load Matplotlib's headless backend."""
    if "MPLCONFIGDIR" not in os.environ:
        config_dir = Path(gettempdir()) / "wikicontrib-matplotlib"
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        else:
            os.environ["MPLCONFIGDIR"] = str(config_dir)

    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot

    return pyplot


plt = _load_pyplot()

BACKGROUND = "#F5F3EE"
INK = "#182126"
MUTED = "#687378"
GRID = "#D7D4CB"
COLORS = {
    "volume": "#31688E",
    "additive": "#35A486",
    "persistence": "#F2A541",
    "discussion": "#A75D9E",
    "maintenance": "#AAB2B5",
}


@dataclass(frozen=True)
class VisualizationManifest:
    """Paths produced by one visualization run."""

    impact_leaderboard: Path
    role_balance: Path
    edit_timeline: Path
    contributor_radars: tuple[Path, ...]

    @property
    def all_paths(self) -> tuple[Path, ...]:
        return (
            self.impact_leaderboard,
            self.role_balance,
            self.edit_timeline,
            *self.contributor_radars,
        )


def generate_visualizations(
    article_title: str,
    revisions: list[RawRevision],
    profiles: ProfileReport,
    impact: ImpactReport,
    output_dir: Path | str,
    *,
    top_n: int = 10,
    radar_count: int = 5,
) -> VisualizationManifest:
    """Generate the Day-13 chart set and return every output path."""
    if top_n <= 0 or radar_count <= 0:
        raise ValueError("top_n and radar_count must be positive")
    if not impact.contributors:
        raise ValueError("cannot visualise an empty impact report")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    radar_dir = output_dir / "radars"

    leaderboard_path = output_dir / "impact_leaderboard.png"
    role_path = output_dir / "additive_maintenance.png"
    timeline_path = output_dir / "edit_timeline.png"

    plot_impact_leaderboard(impact, leaderboard_path, article_title, top_n=top_n)
    plot_role_balance(profiles, role_path, article_title, top_n=top_n)
    plot_edit_timeline(revisions, timeline_path, article_title)

    radar_paths: list[Path] = []
    for result in impact.ranked[:radar_count]:
        stem = _safe_stem(result.user)
        path = radar_dir / f"{result.rank:02d}-{stem}.png"
        plot_contributor_radar(result, path, article_title)
        radar_paths.append(path)

    return VisualizationManifest(
        impact_leaderboard=leaderboard_path,
        role_balance=role_path,
        edit_timeline=timeline_path,
        contributor_radars=tuple(radar_paths),
    )


def plot_impact_leaderboard(
    report: ImpactReport,
    path: Path | str,
    article_title: str,
    *,
    top_n: int = 10,
) -> Path:
    """Plot composite ranks as stacked, per-dimension contributions."""
    results = list(reversed(report.ranked[:top_n]))
    if not results:
        raise ValueError("cannot plot an empty impact report")

    fig_height = max(5.0, 0.55 * len(results) + 2.2)
    fig, ax = plt.subplots(figsize=(11, fig_height), facecolor=BACKGROUND)
    ax.set_facecolor(BACKGROUND)
    users = [result.user for result in results]
    left = [0.0] * len(results)
    for dimension in DIMENSIONS:
        values = [result.contributions[dimension].weighted_value for result in results]
        ax.barh(
            users,
            values,
            left=left,
            height=0.68,
            color=COLORS[dimension],
            label=dimension.title(),
        )
        left = [base + value for base, value in zip(left, values, strict=True)]

    for row, result in enumerate(results):
        ax.text(
            result.score + 0.012,
            row,
            f"{result.score:.3f}",
            va="center",
            color=INK,
            fontsize=9,
            fontweight="bold",
        )

    ax.set_xlim(0, max(1.04, max(result.score for result in results) + 0.12))
    ax.set_xlabel("Composite impact score", color=MUTED, labelpad=10)
    ax.set_title(
        f"Contributor impact — {article_title}",
        loc="left",
        color=INK,
        fontsize=17,
        fontweight="bold",
        pad=18,
    )
    ax.text(
        0,
        1.015,
        "Each bar preserves the weighted contribution of all four model axes.",
        transform=ax.transAxes,
        color=MUTED,
        fontsize=10,
    )
    ax.grid(axis="x", color=GRID, linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK)
    ax.legend(
        ncol=4,
        frameon=False,
        loc="lower left",
        bbox_to_anchor=(0, -0.2),
    )
    _remove_spines(ax)
    return _save_figure(fig, path)


def plot_contributor_radar(
    result: ContributorImpact,
    path: Path | str,
    article_title: str,
) -> Path:
    """Plot one contributor's complete four-axis profile."""
    values = [result.feature_vector[dimension] for dimension in DIMENSIONS]
    angles = [index / len(DIMENSIONS) * 2 * pi for index in range(len(DIMENSIONS))]
    values += values[:1]
    angles += angles[:1]

    fig, ax = plt.subplots(
        figsize=(7.2, 7.2),
        subplot_kw={"polar": True},
        facecolor=BACKGROUND,
    )
    ax.set_facecolor(BACKGROUND)
    ax.plot(angles, values, color=COLORS["volume"], linewidth=2.4)
    ax.fill(angles, values, color=COLORS["volume"], alpha=0.22)
    ax.scatter(angles[:-1], values[:-1], color=COLORS["persistence"], s=48, zorder=3)
    ax.set_xticks(angles[:-1], [dimension.title() for dimension in DIMENSIONS])
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0], [".25", ".50", ".75", "1.0"])
    ax.grid(color=GRID, linewidth=0.9)
    ax.spines["polar"].set_color(GRID)
    ax.tick_params(colors=INK, pad=10)
    ax.set_title(
        f"#{result.rank}  {result.user}",
        color=INK,
        fontsize=17,
        fontweight="bold",
        pad=28,
    )
    fig.text(
        0.5,
        0.05,
        f"{article_title}  •  composite {result.score:.3f}  •  {result.participation_scope}",
        ha="center",
        color=MUTED,
        fontsize=10,
    )
    return _save_figure(fig, path)


def plot_role_balance(
    profiles: ProfileReport,
    path: Path | str,
    article_title: str,
    *,
    top_n: int = 10,
) -> Path:
    """Plot additive versus maintenance edit share for active article editors."""
    selected = sorted(
        (
            profile
            for profile in profiles.contributors.values()
            if profile.article_edits
        ),
        key=lambda profile: (
            -profile.article_edits,
            -profile.gross_words,
            profile.user,
        ),
    )[:top_n]
    if not selected:
        raise ValueError("cannot plot role balance without article editors")
    selected.reverse()

    fig_height = max(5.0, 0.55 * len(selected) + 2.2)
    fig, ax = plt.subplots(figsize=(11, fig_height), facecolor=BACKGROUND)
    ax.set_facecolor(BACKGROUND)
    users = [profile.user for profile in selected]
    additive = [profile.additive_score for profile in selected]
    maintenance = [profile.maintenance_ratio for profile in selected]
    ax.barh(users, additive, color=COLORS["additive"], height=0.68, label="Additive")
    ax.barh(
        users,
        maintenance,
        left=additive,
        color=COLORS["maintenance"],
        height=0.68,
        label="Maintenance",
    )
    for row, profile in enumerate(selected):
        ax.text(
            1.015,
            row,
            f"{profile.article_edits} edits",
            va="center",
            color=MUTED,
            fontsize=9,
        )

    ax.set_xlim(0, 1.14)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_title(
        f"Editing role balance — {article_title}",
        loc="left",
        color=INK,
        fontsize=17,
        fontweight="bold",
        pad=18,
    )
    ax.text(
        0,
        1.015,
        "Most active article editors, split by classified edit orientation.",
        transform=ax.transAxes,
        color=MUTED,
        fontsize=10,
    )
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK)
    ax.legend(frameon=False, ncol=2, loc="lower left", bbox_to_anchor=(0, -0.18))
    _remove_spines(ax)
    return _save_figure(fig, path)


def plot_edit_timeline(
    revisions: list[RawRevision],
    path: Path | str,
    article_title: str,
) -> Path:
    """Plot monthly additive and maintenance edit activity."""
    if not revisions:
        raise ValueError("cannot plot an empty revision history")
    reverts = find_identity_reverts(revisions)
    monthly: dict[datetime, dict[EditType, int]] = defaultdict(
        lambda: {EditType.ADDITIVE: 0, EditType.MAINTENANCE: 0}
    )
    for diff in diff_history(revisions):
        timestamp = datetime.fromisoformat(diff.timestamp.replace("Z", "+00:00"))
        month = datetime(timestamp.year, timestamp.month, 1, tzinfo=timestamp.tzinfo)
        classification = classify_edit(
            diff,
            identity_revert=diff.revid in reverts,
        )
        monthly[month][classification.edit_type] += 1

    observed_months = sorted(monthly)
    months = _month_range(observed_months[0], observed_months[-1])
    additive = [monthly[month][EditType.ADDITIVE] for month in months]
    maintenance = [monthly[month][EditType.MAINTENANCE] for month in months]
    labels = [month.strftime("%Y-%m") for month in months]

    fig_width = max(11.0, min(18.0, 0.42 * len(months) + 5.0))
    fig, ax = plt.subplots(figsize=(fig_width, 6.2), facecolor=BACKGROUND)
    ax.set_facecolor(BACKGROUND)
    x = list(range(len(months)))
    ax.bar(x, additive, color=COLORS["additive"], label="Additive", width=0.78)
    ax.bar(
        x,
        maintenance,
        bottom=additive,
        color=COLORS["maintenance"],
        label="Maintenance",
        width=0.78,
    )
    tick_step = max(1, len(months) // 12)
    shown = x[::tick_step]
    ax.set_xticks(shown, [labels[index] for index in shown], rotation=45, ha="right")
    ax.set_ylabel("Revisions", color=MUTED)
    ax.set_title(
        f"Editing activity over time — {article_title}",
        loc="left",
        color=INK,
        fontsize=17,
        fontweight="bold",
        pad=18,
    )
    ax.text(
        0,
        1.015,
        f"{len(revisions)} revisions grouped by month and classified edit orientation.",
        transform=ax.transAxes,
        color=MUTED,
        fontsize=10,
    )
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK)
    ax.legend(frameon=False, ncol=2, loc="upper right")
    _remove_spines(ax)
    return _save_figure(fig, path)


def _safe_stem(user: str) -> str:
    """Make an untrusted contributor name safe for a local filename."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", user).strip("-.")
    return stem[:80] or "contributor"


def _month_range(start: datetime, end: datetime) -> list[datetime]:
    """Return every calendar month in an inclusive range, preserving gaps."""
    months: list[datetime] = []
    current = start
    while current <= end:
        months.append(current)
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1, tzinfo=current.tzinfo)
        else:
            current = datetime(
                current.year,
                current.month + 1,
                1,
                tzinfo=current.tzinfo,
            )
    return months


def _remove_spines(ax) -> None:
    for spine in ax.spines.values():
        spine.set_visible(False)


def _save_figure(fig, path: Path | str) -> Path:
    """Save a PNG atomically and close the Matplotlib figure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        fig.savefig(
            temporary_path,
            format="png",
            dpi=180,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
        )
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        plt.close(fig)
    return path

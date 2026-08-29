"""Publication figures for GovMembersTN.

Sixteen figures, built offline from `data/processed/` alone. Like the example
scripts in `analysis/`, this reads only the published tables - it never imports
`govtn` and never touches `config/`, so it runs against a `make bundle` archive
with nothing installed but pandas and matplotlib.

Two figures recompute a published quantity rather than re-displaying it (the
Gini in fig. 3, the Lorenz curves in fig. 4) and assert their answer against
`data/processed/indices/`. A figure that silently disagreed with the table it
illustrates would be worse than no figure.

Every figure writes a `.png` (screen), a `.pdf` (vector, for LaTeX) and a
`.csv` of the exact numbers plotted. The CSV is not a convenience: three of the
palette's hues sit below 3:1 against the chart surface, and the table view is
the relief channel that keeps every value readable without relying on colour.

Colours are the validated default palette from the `dataviz` skill, used
unchanged. The categorical slots were checked with its validator under
protanopia and deuteranopia before any of this was written; the three-slot
subset used here passes the all-pairs gate, which is what a node-link scatter
needs; a fourth slot is added only for the line and stacked-bar forms, where
adjacency is the right test. Light mode only - these are print figures.

Usage:  python figures/make_figures.py [--outdir figures]
"""
from __future__ import annotations

import argparse
import pathlib

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import PathPatch
from matplotlib.path import Path

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

# ---------------------------------------------------------------- palette ---
# From dataviz `references/palette.md`, light mode. Not hand-picked, not edited.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# Categorical slots 1-3, in the documented order. Validated all-pairs:
# worst CVD dE 9.2, worst normal-vision dE 24.0.
CAT = ["#2a78d6", "#eb6834", "#1baf7a"]

# A fourth slot, for the adjacent-pairlist forms only (lines, stacked bars).
# Validated adjacent: worst CVD dE 9.1, worst normal-vision dE 22.9. Aqua and
# yellow both sit below 3:1 on the surface, so every chart using this carries
# direct labels and a table twin - which the 4-series rule requires anyway.
CAT4 = CAT + ["#eda100"]

# Diverging poles (warm/cool, so they read as opposite) + neutral midpoint.
DIV_HIGH, DIV_LOW, DIV_MID = "#2a78d6", "#e34948", "#f0efec"

# Sequential blue, steps 100->700. The light end is allowed to recede toward
# the surface here because this ramp encodes magnitude, not order: a cell at
# ~0% coverage SHOULD look empty.
SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
       "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281",
       "#0d366b"]

# Ordinal steps for an ORDERED discrete scale (chronological periods). Unlike
# the sequential ramp above, the light end must still clear 2:1 against the
# surface, and adjacent steps must be visibly apart - so this is a wider-spaced
# subset, validated with the checker's `--ordinal` mode.
ORD = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]

ERA_ORDER = ["beylical", "protectorate", "protectorate_end", "monarchy",
             "bourguiba", "ben_ali", "transition", "second_republic",
             "saied_exception"]

# Short labels. The published `era_label` values are too long for an axis.
ERA_SHORT = {
    "beylical": "Beylical", "protectorate": "Protectorate",
    "protectorate_end": "Protec. end", "monarchy": "Monarchy",
    "bourguiba": "Bourguiba", "ben_ali": "Ben Ali",
    "transition": "Transition", "second_republic": "2nd Republic",
    "saied_exception": "Post-2021",
}


def style() -> None:
    """Recessive chrome. The data is the only thing allowed to be loud."""
    plt.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlecolor": INK,
        "axes.labelsize": 9,
        "axes.labelcolor": INK_2,
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.frameon": False,
        "legend.fontsize": 8,
        "legend.labelcolor": INK_2,
        # Hairline, solid, one shade off the surface. Never dashed.
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "grid.linestyle": "-",
        "lines.linewidth": 2.0,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
    })


K = 0.5523  # circle-to-cubic-Bezier constant


def data_radius(ax, points: float = 3.0) -> tuple[float, float]:
    """A radius in typographic points, expressed in data units per axis.

    The two axes almost never share a scale - percent against era index,
    ratio against governorate - so a single radius in data units renders as a
    visibly squashed corner. Converting through the display transform keeps
    the arc circular on the page. The axis limits must already be set.
    """
    inv = ax.transData.inverted()
    px = points * ax.figure.dpi / 72.0
    (x0, y0), (x1, y1) = inv.transform((0, 0)), inv.transform((px, px))
    return abs(x1 - x0), abs(y1 - y0)


def rounded_bar(ax, x, y, width, height, color, *, horizontal=False,
                flip=False, points=3.0):
    """A bar with its data-end rounded and its baseline end square.

    matplotlib has no such primitive, so the path is built by hand. `flip`
    puts the rounding on the low end, for a diverging bar that grows leftward
    from its baseline.
    """
    x0, x1, y0, y1 = x, x + width, y, y + height
    rx, ry = data_radius(ax, points)
    if horizontal:
        rx = min(rx, abs(width)); ry = min(ry, abs(height) / 2)
    else:
        rx = min(rx, abs(width) / 2); ry = min(ry, abs(height))

    if horizontal and not flip:          # grows right, round the right end
        verts = [(x0, y0), (x1 - rx, y0), (x1 - rx + rx * K, y0),
                 (x1, y0 + ry - ry * K), (x1, y0 + ry),
                 (x1, y1 - ry), (x1, y1 - ry + ry * K),
                 (x1 - rx + rx * K, y1), (x1 - rx, y1), (x0, y1), (x0, y0)]
    elif horizontal:                     # grows left, round the left end
        verts = [(x1, y1), (x0 + rx, y1), (x0 + rx - rx * K, y1),
                 (x0, y1 - ry + ry * K), (x0, y1 - ry),
                 (x0, y0 + ry), (x0, y0 + ry - ry * K),
                 (x0 + rx - rx * K, y0), (x0 + rx, y0), (x1, y0), (x1, y1)]
    else:                                # grows up, round the top
        verts = [(x0, y0), (x0, y1 - ry), (x0, y1 - ry + ry * K),
                 (x0 + rx - rx * K, y1), (x0 + rx, y1),
                 (x1 - rx, y1), (x1 - rx + rx * K, y1),
                 (x1, y1 - ry + ry * K), (x1, y1 - ry), (x1, y0), (x0, y0)]
    codes = [Path.MOVETO, Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO, Path.CLOSEPOLY]
    patch = PathPatch(Path(verts, codes), facecolor=color, edgecolor="none",
                      linewidth=0, zorder=3)
    ax.add_patch(patch)
    return patch


def ink_on(hex_color: str) -> str:
    """White or ink for a label set inside a fill, by the fill's luminance."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    chan = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            for c in (r, g, b)]
    lum = 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2]
    # White only on a genuinely dark fill. Mid steps of the blue ramp are
    # light enough that ink beats white by 2-3x on contrast.
    return "#ffffff" if lum < 0.25 else INK


def _mix(a: str, b: str, t: float) -> str:
    """Blend two hexes, `t` of the way from a to b. Used for the diverging arms.

    The palette documents the two poles and the neutral midpoint, not every
    intermediate step, so the arms are interpolated between exactly those
    documented values rather than eyeballed.
    """
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def seq_color(t: float) -> str:
    """Sample the sequential ramp at t in [0, 1]."""
    if not np.isfinite(t):
        return "#f2f2ef"
    return SEQ[int(round(min(max(t, 0.0), 1.0) * (len(SEQ) - 1)))]


# ------------------------------------------------------------------ data ---
def load():
    read = lambda p: pd.read_csv(p, low_memory=False)
    return dict(
        persons=read(PROCESSED / "persons.csv"),
        appointments=read(PROCESSED / "appointments.csv"),
        cabinets=read(PROCESSED / "cabinets.csv"),
        governorates=read(PROCESSED / "governorates.csv"),
        eras=read(PROCESSED / "eras.csv"),
        gini=read(PROCESSED / "indices" / "representation_gini.csv"),
        ratios=read(PROCESSED / "indices" / "representation_by_governorate.csv"),
        bipartite=read(PROCESSED / "networks" / "edges_bipartite.csv"),
        co=read(PROCESSED / "networks" / "edges_co_membership.csv"),
    )


def lorenz_points(counts: dict, populations: dict) -> list[tuple[float, float]]:
    """Cumulative (population share, minister share), least-represented first.

    Mirrors `govtn.inequality.lorenz`. Every unit in `populations` takes part,
    including those that supplied nobody - dropping the zeros would understate
    the index by exactly the cases that make the point.
    """
    total_pop = sum(populations.values())
    total_min = sum(counts.get(n, 0) for n in populations)
    if not total_pop or not total_min:
        return []
    ordered = sorted(populations, key=lambda n: counts.get(n, 0) / populations[n])
    points, cum_p, cum_m = [(0.0, 0.0)], 0.0, 0.0
    for name in ordered:
        cum_p += populations[name] / total_pop
        cum_m += counts.get(name, 0) / total_min
        points.append((cum_p, cum_m))
    return points


def gini_of(points) -> float | None:
    if len(points) < 2:
        return None
    area = sum((x1 - x0) * (y0 + y1) / 2
               for (x0, y0), (x1, y1) in zip(points, points[1:]))
    return 1 - 2 * area


def era_counts(persons, appointments, era: str) -> dict[str, int]:
    """Coded birth governorates of everyone who served in `era`, counted once."""
    pairs = (appointments[["person_id", "era"]].dropna().drop_duplicates()
             .merge(persons[["person_id", "birth_governorate"]],
                    on="person_id", how="left"))
    block = pairs[pairs["era"] == era]
    return block["birth_governorate"].dropna().value_counts().to_dict()


# --------------------------------------------------------------- figures ---
def fig_coverage(d):
    """Attribute coverage by decade of first appointment - a heatmap.

    The README tells you to read VALIDATION.md before computing any long-run
    trend. This is that warning as a picture: coverage is a property of the
    sources, and it moves by a factor of three across the series.
    """
    persons, app = d["persons"], d["appointments"]
    first = (app.assign(y=pd.to_datetime(app["start_date"], errors="coerce").dt.year)
             .dropna(subset=["y"]).groupby("person_id")["y"].min())
    dec = (first // 10 * 10).astype(int)
    dec = dec[dec >= 1940]

    variables = [("wikidata_qid", "Wikidata QID"), ("gender", "Gender"),
                 ("occupations", "Occupation"), ("birth_date", "Birth date"),
                 ("birth_place", "Birthplace"), ("parties", "Party"),
                 ("education", "Education")]
    decades = sorted(dec.unique())
    idx = persons.set_index("person_id")

    grid, ns = [], []
    for _, col in [(0, c) for c, _ in variables]:
        row = []
        for dd in decades:
            ids = dec[dec == dd].index
            sub = idx.reindex(ids)
            row.append(sub[col].notna().mean() * 100 if len(sub) else np.nan)
        grid.append(row)
    for dd in decades:
        ns.append(int((dec == dd).sum()))
    grid = np.array(grid, dtype=float)

    fig, ax = plt.subplots(figsize=(7.6, 3.5))
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            v = grid[i, j]
            c = seq_color(v / 100)
            # A 2px surface gap does the separating; never a stroke.
            ax.add_patch(plt.Rectangle((j + 0.03, i + 0.03), 0.94, 0.94,
                                       facecolor=c, edgecolor="none"))
            if np.isfinite(v):
                ax.text(j + 0.5, i + 0.5, f"{v:.0f}", ha="center", va="center",
                        fontsize=7.5, color=ink_on(c))
    ax.set_xlim(0, grid.shape[1]); ax.set_ylim(grid.shape[0], 0)
    ax.set_xticks(np.arange(len(decades)) + 0.5)
    ax.set_xticklabels([f"{dd}s\nn={n}" for dd, n in zip(decades, ns)])
    ax.set_yticks(np.arange(len(variables)) + 0.5)
    ax.set_yticklabels([lab for _, lab in variables])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("Person-level attribute coverage, by decade of first appointment")
    ax.text(0, -0.30, "Cells are % of that decade's entrants carrying the "
                      "attribute. Coverage is a fact about the sources, not "
                      "the people —\nread it before any long-run trend.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")

    table = pd.DataFrame(grid.round(1), columns=[f"{dd}s" for dd in decades],
                         index=[lab for _, lab in variables])
    table.index.name = "variable"
    fig.tight_layout()
    return fig, table.reset_index()


def fig_women(d):
    """Share of women, by era. One series, so no legend box - the title names it."""
    app, persons = d["appointments"], d["persons"]
    pairs = (app[["person_id", "era"]].dropna().drop_duplicates()
             .merge(persons[["person_id", "gender"]], on="person_id", how="left"))
    rows = []
    for era in ERA_ORDER:
        block = pairs[pairs["era"] == era]
        known = block[block["gender"].notna()]
        if len(known) < 5:
            continue
        women = int((known["gender"].str.lower() == "female").sum())
        rows.append({"era": era, "era_label": ERA_SHORT[era],
                     "ministers_with_known_gender": len(known), "women": women,
                     "share_women_pct": round(women / len(known) * 100, 1)})
    table = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    ax.set_axisbelow(True)
    ax.yaxis.grid(True); ax.xaxis.grid(False)
    # Limits first: the corner radius is resolved through the display
    # transform, so it needs the final scale.
    ax.set_ylim(0, max(table["share_women_pct"]) * 1.28)
    ax.set_xlim(-0.7, len(table) - 0.3)
    for i, r in table.iterrows():
        rounded_bar(ax, i - 0.225, 0, 0.45, r["share_women_pct"], CAT[0])
    # Label selectively: the first era with any women, and the endpoint.
    nz = table[table["share_women_pct"] > 0]
    for i in ([nz.index[0], table.index[-1]] if len(nz) else []):
        r = table.loc[i]
        ax.text(i, r["share_women_pct"] + 0.9, f"{r['share_women_pct']:.1f}%",
                ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.set_xticks(range(len(table)))
    ax.set_xticklabels(table["era_label"], rotation=20, ha="right")
    ax.set_ylabel("% of ministers")
    ax.set_title("Women as a share of ministers, by regime era")
    ax.text(0, -0.42, "Denominator is ministers whose gender is coded, not all "
                      "ministers; see fig. 1 for how that coverage moves.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    fig.tight_layout()
    return fig, table


def fig_gini(d):
    """Territorial representation Gini per era, three partitions.

    Recomputed from the raw tables and checked against the published index.
    Eras the index withholds stay visibly absent rather than interpolated.
    """
    gini = d["gini"]
    gov = d["governorates"]
    pops = dict(zip(gov["governorate"], gov["population"]))
    greater_tunis = set(gov.loc[gov["region_type"] == "greater_tunis",
                                "governorate"])

    def partition(units):
        if units == "governorate":
            return {g: g for g in pops}
        if units == "greater_tunis_merged":
            return {g: ("Greater Tunis" if g in greater_tunis else g) for g in pops}
        return dict(zip(gov["governorate"], gov["region_type"]))

    rows = []
    for units in ("governorate", "greater_tunis_merged", "region"):
        mapping = partition(units)
        unit_pop: dict[str, int] = {}
        for g, p in pops.items():
            unit_pop[mapping[g]] = unit_pop.get(mapping[g], 0) + p
        for era in ERA_ORDER:
            counts: dict[str, float] = {}
            for g, n in era_counts(d["persons"], d["appointments"], era).items():
                if g in mapping:
                    counts[mapping[g]] = counts.get(mapping[g], 0) + n
            rows.append({"era": era, "units": units,
                         "gini_recomputed": gini_of(lorenz_points(counts, unit_pop))})
    mine = pd.DataFrame(rows)

    merged = gini.merge(mine, on=["era", "units"], how="left")
    check = merged.dropna(subset=["gini_representation", "gini_recomputed"])
    worst = float((check["gini_representation"] - check["gini_recomputed"]).abs().max())
    assert worst < 5e-4, f"recomputed Gini disagrees with the published index by {worst}"

    fig, ax = plt.subplots(figsize=(7.0, 3.9))
    ax.set_axisbelow(True)
    ax.yaxis.grid(True); ax.xaxis.grid(False)
    xs = {e: i for i, e in enumerate(ERA_ORDER)}
    labels = {"governorate": "24 governorates",
              "greater_tunis_merged": "Greater Tunis merged", "region": "7 regions"}

    for slot, units in enumerate(["governorate", "greater_tunis_merged", "region"]):
        block = gini[(gini["units"] == units) &
                     gini["gini_representation"].notna()].copy()
        block["x"] = block["era"].map(xs)
        block = block.sort_values("x").reset_index(drop=True)

        # Split into runs of eras that are ADJACENT in the era order. Drawing
        # one continuous line would interpolate straight through the eras the
        # index refuses to report, which is the opposite of what withholding
        # them means.
        runs, current = [], [0]
        for i in range(1, len(block)):
            if block.loc[i, "x"] - block.loc[i - 1, "x"] == 1:
                current.append(i)
            else:
                runs.append(current); current = [i]
        runs.append(current)

        for run in runs:
            seg = block.loc[run]
            if len(seg) > 1:
                ax.fill_between(seg["x"], seg["ci_low"], seg["ci_high"],
                                color=CAT[slot], alpha=0.10, linewidth=0)
                ax.plot(seg["x"], seg["gini_representation"], color=CAT[slot],
                        lw=2.0, zorder=4)
        # A thin connector across a withheld stretch: the eye still follows the
        # series, but the segment is visibly not a measurement.
        for a, b in zip(runs, runs[1:]):
            end, start = block.loc[a[-1]], block.loc[b[0]]
            ax.plot([end["x"], start["x"]],
                    [end["gini_representation"], start["gini_representation"]],
                    color=CAT[slot], lw=0.9, alpha=0.45, zorder=3)
        ax.plot(block["x"], block["gini_representation"], color=CAT[slot],
                linestyle="none", marker="o", markersize=5,
                markeredgecolor=SURFACE, markeredgewidth=2, zorder=5)
        last = block.iloc[-1]
        ax.text(last["x"] + 0.18, last["gini_representation"],
                f"{last['gini_representation']:.2f}", va="center",
                fontsize=8, color=INK_2)

    withheld = sorted({xs[e] for e in
                       gini.loc[gini["gini_representation"].isna(), "era"]})
    for x in withheld:
        ax.axvspan(x - 0.5, x + 0.5, color=DIV_MID, zorder=0)
    ax.text(np.mean(withheld[:3]) if withheld else 0, 0.06,
            "withheld:\ntoo few coded", ha="center", fontsize=7, color=MUTED)

    ax.set_xticks(list(xs.values()))
    ax.set_xticklabels([ERA_SHORT[e] for e in ERA_ORDER], rotation=20, ha="right")
    ax.set_xlim(-0.6, len(ERA_ORDER) - 0.1)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Representation Gini")
    ax.set_title("Territorial inequality in ministerial recruitment, by era")
    handles = [Line2D([], [], color=CAT[i], lw=2, label=labels[u])
               for i, u in enumerate(["governorate", "greater_tunis_merged", "region"])]
    ax.legend(handles=handles, loc="upper right", ncol=1)
    ax.text(0, -0.40, "Bands are 95% bootstrap intervals. Read the trend, not "
                      "the level: the level depends on the partition, which is "
                      "why all three are shown.\nShaded eras are withheld by the "
                      "index for insufficient coverage.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    fig.tight_layout()
    return fig, merged[["era", "units", "ministers", "coded", "coverage",
                        "gini_representation", "ci_low", "ci_high",
                        "gini_recomputed", "basis"]]


def fig_lorenz(d):
    """The Lorenz curves behind the index - described in the code, never drawn.

    Emphasis form: the two eras that bound the range carry the accent hues,
    the rest are context.
    """
    gov = d["governorates"]
    pops = dict(zip(gov["governorate"], gov["population"]))
    reported = [e for e in ERA_ORDER
                if not d["gini"][(d["gini"]["units"] == "governorate") &
                                 (d["gini"]["era"] == e)]["gini_representation"]
                .isna().all()]

    curves, rows = {}, []
    for era in reported:
        pts = lorenz_points(era_counts(d["persons"], d["appointments"], era), pops)
        curves[era] = pts
        for x, y in pts:
            rows.append({"era": era, "cum_population_share": round(x, 4),
                         "cum_minister_share": round(y, 4)})

    highlight = {reported[0]: CAT[0], reported[-1]: CAT[1]}
    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    ax.set_axisbelow(True); ax.grid(True)
    # The parity diagonal is chrome, so it sits a shade off the surface and
    # below every curve; the context eras are data, so they read darker.
    ax.plot([0, 1], [0, 1], color=AXIS, lw=1.0, zorder=1)
    ax.text(0.62, 0.615, "parity", rotation=45, fontsize=7.5, color=MUTED,
            ha="center", va="bottom", rotation_mode="anchor")

    for era, pts in curves.items():
        x, y = zip(*pts)
        accent = highlight.get(era)
        ax.plot(x, y, color=accent or "#a9a8a1", lw=2.0 if accent else 1.3,
                zorder=4 if accent else 2)
    # The G values ride the legend rather than the curves: at the right-hand
    # end every series converges on (1,1), so direct labels there collide.
    ax.set_xlim(0, 1.03); ax.set_ylim(0, 1.03)
    ax.set_xlabel("Cumulative share of population")
    ax.set_ylabel("Cumulative share of ministers")
    ax.set_title("Lorenz curves of ministerial recruitment")
    handles = [
        Line2D([], [], color=CAT[0], lw=2,
               label=f"{ERA_SHORT[reported[0]]}  (G = {gini_of(curves[reported[0]]):.2f})"),
        Line2D([], [], color=CAT[1], lw=2,
               label=f"{ERA_SHORT[reported[-1]]}  (G = {gini_of(curves[reported[-1]]):.2f})"),
        Line2D([], [], color="#a9a8a1", lw=1.3, label="other reported eras")]
    ax.legend(handles=handles, loc="upper left")
    ax.text(0, -0.16, "Governorates ordered least-represented first. The gap to "
                      "the diagonal is the index.", transform=ax.transAxes,
            fontsize=7.5, color=MUTED, va="top")
    fig.tight_layout()
    return fig, pd.DataFrame(rows)


def fig_governorates(d):
    """Over- and under-representation by governorate - a diverging bar.

    Polarity, not magnitude: parity is the meaningful midpoint, so the form is
    diverging (two hues that read as opposite) anchored at 1.0.
    """
    r = d["ratios"].sort_values("ratio").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(6.2, 6.4))
    ax.set_axisbelow(True)
    ax.xaxis.grid(True); ax.yaxis.grid(False)

    ax.set_yticks(range(len(r)))
    ax.set_yticklabels(r["governorate"])
    ax.set_ylim(-0.8, len(r) - 0.2)
    ax.set_xlim(-0.45, 4.05)
    for i, row in r.iterrows():
        above = row["ratio"] >= 1
        lo, hi = min(1.0, row["ratio"]), max(1.0, row["ratio"])
        rounded_bar(ax, lo, i - 0.22, hi - lo, 0.44,
                    DIV_HIGH if above else DIV_LOW,
                    horizontal=True, flip=not above)
    for i, row in r.iterrows():
        side = 1 if row["ratio"] >= 1 else -1
        ax.text(row["ratio"] + 0.10 * side, i,
                f"{row['ratio']:.2f}", va="center",
                ha="left" if side > 0 else "right", fontsize=7.5, color=INK_2)

    ax.axvline(1.0, color=AXIS, lw=1.2, zorder=2)
    ax.set_xlabel("Ministers per capita, relative to parity (1.0)")
    ax.set_title("Which governorates are over- and under-represented")
    handles = [Line2D([], [], color=DIV_HIGH, lw=6, label="above parity"),
               Line2D([], [], color=DIV_LOW, lw=6, label="below parity")]
    ax.legend(handles=handles, loc="lower right")
    ax.text(0, -0.09, "Share of coded ministers ÷ share of 2024 census "
                      "population. Rests on the 54% of people with a coded "
                      "birthplace.", transform=ax.transAxes, fontsize=7.5,
            color=MUTED, va="top")
    fig.tight_layout()
    return fig, r


def fig_network(d):
    """Elite continuity between cabinets: an edge is a shared minister.

    Deliberately NOT the person-level co-membership graph. That one has 832
    nodes and 35,211 ties even after discarding every pair who overlapped less
    than a year, and drawn as a node-link it is a hairball - a picture with no
    readable claim in it. Aggregating to the cabinet collapses it to 56 nodes
    and makes the actual structure legible: governments chain to their
    neighbours in time through the ministers they keep.

    Chronology is an ordered scale, so the colour job is ORDINAL - one hue in
    monotone steps - not categorical. Swapping two periods would change the
    meaning, which is the test.
    """
    import networkx as nx

    bip, cab = d["bipartite"], d["cabinets"].copy()
    cab["start"] = pd.to_datetime(cab["start_date"], errors="coerce")
    cab = cab.dropna(subset=["start"]).sort_values("start")
    keep = set(cab["cabinet_id"])

    members = {c: set(g["person_id"])
               for c, g in bip[bip["cabinet_id"].isin(keep)].groupby("cabinet_id")}
    g = nx.Graph()
    for c in cab["cabinet_id"]:
        g.add_node(c)
    ids = list(cab["cabinet_id"])
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            shared = len(members.get(a, set()) & members.get(b, set()))
            if shared:
                g.add_edge(a, b, weight=shared)

    # Five ordered periods -> the five validated ordinal steps.
    bounds = [("Pre-1957", 1957, ORD[0]), ("Bourguiba 1957–87", 1987, ORD[1]),
              ("Ben Ali 1987–2011", 2011, ORD[2]),
              ("2011–2021", 2021, ORD[3]), ("Post-2021", 9999, ORD[4])]

    def period(year):
        for label, upper, color in bounds:
            if year < upper:
                return label, color
        return bounds[-1][0], bounds[-1][2]

    years = dict(zip(cab["cabinet_id"], cab["start"].dt.year))
    sizes_by = dict(zip(cab["cabinet_id"], cab["n_members"].fillna(0)))
    mx = max(sizes_by.values()) or 1

    pos = nx.spring_layout(g, seed=20260827, k=0.55, iterations=200)

    fig, ax = plt.subplots(figsize=(7.4, 6.4))
    widths = [0.25 + 1.9 * (g[u][v]["weight"] / 25) for u, v in g.edges]
    nx.draw_networkx_edges(g, pos, ax=ax, edge_color="#dedcd4", width=widths,
                           alpha=0.75)
    for label, _, color in bounds:
        nodes = [n for n in g.nodes if period(years[n])[0] == label]
        if not nodes:
            continue
        nx.draw_networkx_nodes(
            g, pos, nodelist=nodes, ax=ax, node_color=color,
            node_size=[60 + 340 * (sizes_by[n] / mx) for n in nodes],
            edgecolors=SURFACE, linewidths=1.6)  # surface ring, not a border

    # Direct-label only the extremes of the chain, not all 56. The three most
    # connected cabinets sit close together, so the labels are fanned to
    # distinct sides and tied back with leader lines - stacking them upward
    # would detach each from its node.
    by_deg = sorted(g.degree(weight="weight"), key=lambda kv: -kv[1])[:3]
    offsets = [(26, 26), (34, -20), (-30, -30)]
    for (node, _), (dx, dy) in zip(by_deg, offsets):
        short = node.replace("Gouvernement ", "")
        short = short if len(short) <= 22 else short[:21] + "…"
        ax.annotate(short, xy=pos[node], xytext=(dx, dy),
                    textcoords="offset points", fontsize=7.5, color=INK,
                    ha="left" if dx > 0 else "right", va="center",
                    arrowprops=dict(arrowstyle="-", color=AXIS, lw=0.8,
                                    shrinkA=0, shrinkB=6))

    ax.set_axis_off()
    ax.set_title("Elite continuity between cabinets, 1943–2026")
    handles = [Line2D([], [], marker="o", linestyle="none", markersize=8,
                      markerfacecolor=c, markeredgecolor=SURFACE, label=lab)
               for lab, _, c in bounds]
    ax.legend(handles=handles, loc="upper left", ncol=1, title="Cabinet formed",
              title_fontsize=8)
    ax.text(0, -0.01,
            f"{g.number_of_nodes()} cabinets, {g.number_of_edges()} pairs sharing "
            f"at least one minister. Edge width is ministers in common; node "
            f"size is cabinet size.\nThe three most-connected cabinets are "
            f"labelled. Drawn at the cabinet level because the 832-minister "
            f"graph is an unreadable hairball.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")

    table = (pd.DataFrame(
        [{"cabinet_a": u, "cabinet_b": v, "shared_ministers": g[u][v]["weight"],
          "year_a": years[u], "year_b": years[v]} for u, v in g.edges])
        .sort_values("shared_ministers", ascending=False))
    fig.tight_layout()
    return fig, table


# ------------------------------------------------- shared for figures 7-16 ---
# Eras with enough personally-dated appointments to carry a distribution.
DURATION_ERAS = ["bourguiba", "ben_ali", "transition", "second_republic"]

# Seniority, least senior first, so the ordinal ramp runs light -> dark with it.
RANK_TIERS = [
    ("Secretary of state", {5, 6}),
    ("Minister", {3}),
    ("Minister of state / delegate", {2, 4}),
    ("Head of government", {0}),
]

REGION_FOLD = {
    "greater_tunis": "Greater Tunis",
    "centre_east": "Centre-East (Sahel)",
    "northeast": "Other coastal",
    "southeast": "Other coastal",
    "northwest": "Interior",
    "centre_west": "Interior",
    "southwest": "Interior",
}
REGION_ORDER = ["Greater Tunis", "Centre-East (Sahel)", "Other coastal", "Interior"]


def personal_tenures(appointments: pd.DataFrame) -> pd.DataFrame:
    """Appointments whose dates describe the PERSON, not their cabinet.

    `build` says it outright: a roster row with no individual dates inherits
    the cabinet's span, which is an upper bound on a tenure and not a tenure.
    Every duration figure here filters on `date_basis` for that reason, and
    drops the rows whose end date the pipeline already flagged unreliable -
    that alone takes the 20-year-plus "tenures" from 108 to 22.
    """
    return appointments[
        appointments["date_basis"].isin(["statement", "row"])
        & ~appointments["end_date_unreliable"].fillna(False)
        & appointments["tenure_days"].notna()
    ].copy()


def stacked_bar(ax, x, shares, colors, width=0.5, gap_pts=1.0):
    """A stacked column whose segments are separated by surface, not strokes."""
    _, gap = data_radius(ax, gap_pts)
    bottom = 0.0
    for value, color in zip(shares, colors):
        if value <= 0:
            continue
        top = bottom + value
        inner = max(top - bottom - gap, 1e-9)
        ax.add_patch(plt.Rectangle((x - width / 2, bottom), width, inner,
                                   facecolor=color, edgecolor="none", zorder=3))
        bottom = top
    return bottom


def km_curve(durations, events):
    """Kaplan-Meier survival, written out rather than pulled in.

    `lifelines` for one estimator would be a dependency the rest of the
    repository does not need. Returns step points (t, S(t)).
    """
    order = np.argsort(durations)
    d, e = np.asarray(durations)[order], np.asarray(events)[order]
    n = len(d)
    points, surv, at_risk, i = [(0.0, 1.0)], 1.0, n, 0
    while i < n:
        t = d[i]
        tied = (d == t)
        deaths = int(e[tied].sum())
        if deaths:
            surv *= 1 - deaths / at_risk
            points.append((float(t), surv))
        at_risk -= int(tied.sum())
        i += int(tied.sum())
    return points


# --------------------------------------------------------- figures 7 to 16 ---
def fig_government_size(d):
    """How many people hold ministerial office in a given year.

    Deliberately NOT `cabinets.n_members` plotted against formation date.
    Some cabinet articles cover a whole spell of reshuffles as one roster, so
    that column ranges up to 181 for a single "cabinet" - a fact about how
    the source chunks its rosters, not about the size of a Tunisian
    government. Counting distinct people in office in each year is robust to
    the chunking, and is the quantity anyone actually means.
    """
    app = d["appointments"].copy()
    cab_end = dict(zip(d["cabinets"]["cabinet_id"],
                       pd.to_datetime(d["cabinets"]["end_date"], errors="coerce")))
    snapshot = pd.Timestamp("2026-08-26")
    app["s"] = pd.to_datetime(app["start_date"], errors="coerce")
    app["e"] = pd.to_datetime(app["end_date"], errors="coerce")
    app = app.dropna(subset=["s", "person_id"])
    # A missing end date is filled from the CABINET, and only runs to the
    # snapshot where the cabinet itself has no end either - i.e. where the
    # government is still sitting. `is_incumbent` is just `end_date.isna()`,
    # so carrying every such row to the snapshot would keep a 1969 justice
    # minister in office until 2026 and roughly triple every recent year;
    # dropping them all instead empties the last two years, because current
    # ministers have no end date by definition.
    fallback = app["cabinet_id"].map(cab_end)
    app["e"] = app["e"].fillna(fallback).mask(
        app["e"].isna() & fallback.isna(), snapshot)
    app = app.dropna(subset=["e"])
    app = app[app["e"] >= app["s"]]

    years = list(range(1956, 2027))
    rows = []
    for y in years:
        lo, hi = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-12-31")
        live = app[(app["s"] <= hi) & (app["e"] >= lo)]
        rows.append({"year": y, "people_in_office": live["person_id"].nunique(),
                     "appointments_live": len(live)})
    table = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(7.2, 3.5))
    ax.set_axisbelow(True); ax.yaxis.grid(True); ax.xaxis.grid(False)
    ax.set_xlim(1954, 2028)
    ax.set_ylim(0, table["people_in_office"].max() * 1.2)
    ax.plot(table["year"], table["people_in_office"], color=CAT[0], lw=2.0,
            zorder=4)
    peak = table.loc[table["people_in_office"].idxmax()]
    ax.annotate(f"{int(peak['year'])}: {int(peak['people_in_office'])}",
                xy=(peak["year"], peak["people_in_office"]), xytext=(6, 4),
                textcoords="offset points", fontsize=8, color=INK_2)
    last = table.iloc[-1]
    ax.set_ylabel("People holding a ministerial post")
    ax.set_title("The size of the Tunisian government, 1956–2026")
    ax.text(0, -0.22, "Distinct people with an appointment recorded as active "
                      "at any point in the year. An appointment with no end date "
                      "is bounded by its\ncabinet, never carried to the "
                      "snapshot. The 1990s–2000s plateau is inflated where a "
                      "source roster lumps a whole spell of reshuffles\ninto one "
                      "cabinet — read the level loosely, the shape closely.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    fig.tight_layout()
    return fig, table


def fig_rank_composition(d):
    """Seniority mix per era. Ordered categories, so a one-hue ordinal ramp."""
    app = d["appointments"]
    rows = []
    for era in ERA_ORDER:
        block = app[app["era"] == era]
        if len(block) < 20:
            continue
        row = {"era": era, "era_label": ERA_SHORT[era], "n": len(block)}
        for label, levels in RANK_TIERS:
            row[label] = float((block["rank_level"].isin(levels)).mean())
        rows.append(row)
    table = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(7.0, 3.9))
    ax.set_axisbelow(True); ax.yaxis.grid(True); ax.xaxis.grid(False)
    ax.set_ylim(0, 1.0); ax.set_xlim(-0.7, len(table) - 0.3)
    colors = ORD[:2] + ORD[3:5]
    for i, r in table.iterrows():
        stacked_bar(ax, i, [r[label] for label, _ in RANK_TIERS], colors)
    # 4 series: direct labels are mandatory, so the largest tier carries one.
    for i, r in table.iterrows():
        share = r["Minister"]
        base = r["Secretary of state"]
        if share > 0.18:
            ax.text(i, base + share / 2, f"{share:.0%}", ha="center",
                    va="center", fontsize=7.5, color=ink_on(colors[1]))
    ax.set_xticks(range(len(table)))
    ax.set_xticklabels(table["era_label"], rotation=20, ha="right")
    ax.set_yticks([0, .25, .5, .75, 1])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_ylabel("Share of appointments")
    ax.set_title("Seniority of ministerial appointments, by era")
    handles = [Line2D([], [], color=c, lw=7, label=label)
               for (label, _), c in zip(RANK_TIERS, colors)]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.28),
              ncol=2)
    ax.text(0, -0.52, "Rank is parsed separately from portfolio: a secretary of "
                      "state for finance is not the finance minister.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    fig.tight_layout()
    return fig, table


def fig_survival(d):
    """How long a ministerial appointment lasts, by the regime that made it.

    Kaplan-Meier, so the handful of tenures still open at the snapshot are
    censored rather than counted as short.
    """
    tenures = personal_tenures(d["appointments"])
    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    ax.set_axisbelow(True); ax.grid(True)
    ax.set_xlim(0, 12); ax.set_ylim(0, 1.02)

    rows = []
    for slot, era in enumerate(DURATION_ERAS):
        block = tenures[tenures["era"] == era]
        if len(block) < 40:
            continue
        years = block["tenure_days"].to_numpy() / 365.25
        observed = block["end_date"].notna().to_numpy()
        pts = km_curve(years, observed)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        ax.step(xs, ys, where="post", color=CAT4[slot], lw=2.0, zorder=4)
        median = next((t for t, s in pts if s <= 0.5), None)
        rows.append({"era": era, "era_label": ERA_SHORT[era], "n": len(block),
                     "censored": int((~observed).sum()),
                     "median_years": round(median, 2) if median else None})
        if median:
            ax.plot([median], [0.5], marker="o", markersize=7, color=CAT4[slot],
                    markeredgecolor=SURFACE, markeredgewidth=2, zorder=5)
    table = pd.DataFrame(rows)

    ax.axhline(0.5, color=AXIS, lw=1.0, zorder=1)
    ax.text(11.8, 0.52, "median", ha="right", fontsize=7.5, color=MUTED)
    ax.set_xlabel("Years in post")
    ax.set_ylabel("Share still in post")
    ax.set_title("Survival in office, by the regime that made the appointment")
    handles = [Line2D([], [], color=CAT4[i], lw=2,
                      label=f"{r['era_label']}  (median {r['median_years']:.1f}y, "
                            f"n={r['n']})")
               for i, (_, r) in enumerate(table.iterrows())]
    ax.legend(handles=handles, loc="upper right")
    ax.text(0, -0.16, "Only appointments whose dates describe the person rather "
                      "than their cabinet — an inherited cabinet span is an upper "
                      "bound, not a tenure.\nBefore 2011 a missing end date is "
                      "usually a gap in the sources rather than an open tenure; "
                      "12 such rows are censored here.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    fig.tight_layout()
    return fig, table


def fig_turnover(d):
    """Appointments made per year, against how many were new faces."""
    app = d["appointments"].copy()
    app["year"] = pd.to_numeric(app["start_year"], errors="coerce")
    app = app[(app["year"] >= 1956) & (app["year"] <= 2026)]
    per_year = app.groupby("year").size()
    first = app[app["is_first_appointment"].fillna(False)].groupby("year").size()
    years = sorted(set(per_year.index))
    table = pd.DataFrame({
        "year": years,
        "appointments": [int(per_year.get(y, 0)) for y in years],
        "first_time_entrants": [int(first.get(y, 0)) for y in years],
    })
    table["renewal_rate"] = (table["first_time_entrants"]
                             / table["appointments"]).round(3)

    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    ax.set_axisbelow(True); ax.yaxis.grid(True); ax.xaxis.grid(False)
    ax.set_xlim(1955, 2028)
    ax.set_ylim(0, table["appointments"].max() * 1.2)
    # Both series are counts of appointments, so they share one axis. A rate
    # against a count would need a second scale, which is never worth it.
    ax.plot(table["year"], table["appointments"], color=CAT[0], lw=2.0, zorder=4)
    ax.plot(table["year"], table["first_time_entrants"], color=CAT[1], lw=2.0,
            zorder=4)
    peak = table.loc[table["appointments"].idxmax()]
    ax.annotate(f"{int(peak['year'])}: {int(peak['appointments'])}",
                xy=(peak["year"], peak["appointments"]), xytext=(6, 6),
                textcoords="offset points", fontsize=7.5, color=INK_2)
    ax.set_ylabel("Appointments beginning that year")
    ax.set_title("Ministerial turnover and renewal, 1956–2026")
    ax.legend(handles=[Line2D([], [], color=CAT[0], lw=2, label="all appointments"),
                       Line2D([], [], color=CAT[1], lw=2, label="first-time entrants")],
              loc="upper left")
    ax.text(0, -0.20, "The gap between the lines is recycling: appointments "
                      "going to people who had already served. Both are counts, "
                      "so they share one axis.\nSpikes are cabinet formations. "
                      "The flat 1960s are thin sources, not calm politics — see "
                      "fig. 1.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    fig.tight_layout()
    return fig, table


def fig_sovereign_timeline(d):
    """Who held the sovereign portfolios, and for how long.

    One row per portfolio, one segment per continuous holding. The same person
    in the same office turns up under several rows - a French roster line, an
    Arabic one, a Wikidata statement, each tied to a different cabinet - so
    spans are merged per (portfolio, person) rather than drawn once each, or
    the row would be a pile of overlapping duplicates.
    """
    app = d["appointments"].copy()
    order = ["head_of_government", "interior", "foreign_affairs", "defence",
             "finance", "justice"]
    labels = {"head_of_government": "Head of government", "interior": "Interior",
              "foreign_affairs": "Foreign affairs", "defence": "Defence",
              "finance": "Finance", "justice": "Justice"}
    app["s"] = pd.to_datetime(app["start_date"], errors="coerce")
    app["e"] = pd.to_datetime(app["end_date"], errors="coerce")
    snapshot = pd.Timestamp("2026-08-26")
    app["e"] = app["e"].fillna(snapshot)

    # Personally-dated rows only. On cabinet-inherited spans every holder
    # stretches across a whole cabinet, successive cabinets overlap, and the
    # row renders as one solid block that says nothing.
    app = personal_tenures(app.assign(
        s=pd.to_datetime(app["start_date"], errors="coerce"),
        e=pd.to_datetime(app["end_date"], errors="coerce")))
    app["e"] = app["e"].fillna(snapshot)

    rows = []
    for portfolio in order:
        block = app[(app["portfolio"] == portfolio) & app["s"].notna()
                    & app["person_id"].notna() & (app["s"].dt.year >= 1955)]
        spans = []
        for person, grp in block.groupby("person_id"):
            merged = []
            for s, e in sorted(zip(grp["s"], grp["e"])):
                if merged and s <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], e))
                else:
                    merged.append((s, e))
            name = (grp["person_name"].dropna().iloc[0]
                    if grp["person_name"].notna().any() else person)
            spans += [(s, e, person, name) for s, e in merged]
        # One office, one holder at a time: truncate each span where the next
        # holder's begins, so a row reads as succession rather than a pile.
        spans.sort()
        for i, (s, e, person, name) in enumerate(spans):
            end = min(e, spans[i + 1][0]) if i + 1 < len(spans) else e
            if end <= s:
                continue
            rows.append({"portfolio": portfolio,
                         "portfolio_label": labels[portfolio],
                         "person_id": person, "person_name": name,
                         "start": s, "end": end})
    table = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    ax.set_axisbelow(True); ax.xaxis.grid(True); ax.yaxis.grid(False)
    ax.set_xlim(1954, 2028); ax.set_ylim(len(order) - 0.4, -0.7)
    # Two steps of one hue, alternating purely so neighbours separate. The
    # shade carries no meaning - the 2px surface gap alone is too subtle where
    # a holding lasts three months.
    shades = [ORD[2], ORD[0]]
    for i, portfolio in enumerate(order):
        block = table[table["portfolio"] == portfolio].sort_values("start")
        for k, (_, r) in enumerate(block.iterrows()):
            x0 = r["start"].year + r["start"].dayofyear / 365.25
            x1 = r["end"].year + r["end"].dayofyear / 365.25
            ax.add_patch(plt.Rectangle((x0, i - 0.26), max(x1 - x0, 0.12), 0.52,
                                       facecolor=shades[k % 2], edgecolor=SURFACE,
                                       linewidth=1.0, zorder=3))
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([labels[p] for p in order])
    ax.set_xlabel("Year")
    ax.set_title("Succession in the six sovereign portfolios")
    ax.text(0, -0.30, "Each block is one holder's continuous run, truncated "
                      "where the next holder's begins. Alternating shades only "
                      "separate neighbours;\nthey carry no meaning. Gaps are "
                      "years with no personally-dated record, not vacancies — "
                      f"{len(table)} holdings across the six offices.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    fig.tight_layout()
    out = table.copy()
    out["start"] = out["start"].dt.date; out["end"] = out["end"].dt.date
    return fig, out.sort_values(["portfolio", "start"])


def fig_regional_composition(d):
    """Where ministers came from, era by era, among those with a coded birthplace."""
    app, persons = d["appointments"], d["persons"]
    pairs = (app[["person_id", "era"]].dropna().drop_duplicates()
             .merge(persons[["person_id", "birth_region_type"]],
                    on="person_id", how="left"))
    pairs["fold"] = pairs["birth_region_type"].map(REGION_FOLD)

    rows = []
    for era in ERA_ORDER:
        block = pairs[pairs["era"] == era]
        coded = block[block["fold"].notna()]
        if len(coded) < 25:
            continue
        row = {"era": era, "era_label": ERA_SHORT[era], "ministers": len(block),
               "coded": len(coded),
               "coverage": round(len(coded) / len(block), 3)}
        for region in REGION_ORDER:
            row[region] = float((coded["fold"] == region).mean())
        rows.append(row)
    table = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.set_axisbelow(True); ax.yaxis.grid(True); ax.xaxis.grid(False)
    ax.set_ylim(0, 1.0); ax.set_xlim(-0.7, len(table) - 0.3)
    colors = CAT4
    for i, r in table.iterrows():
        stacked_bar(ax, i, [r[region] for region in REGION_ORDER], colors)
    for i, r in table.iterrows():
        share = r["Greater Tunis"]
        if share > 0.12:
            ax.text(i, share / 2, f"{share:.0%}", ha="center", va="center",
                    fontsize=7.5, color=ink_on(colors[0]))
    ax.set_xticks(range(len(table)))
    ax.set_xticklabels([f"{r['era_label']}\nn={r['coded']}"
                        for _, r in table.iterrows()], rotation=20, ha="right")
    ax.set_yticks([0, .25, .5, .75, 1])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_ylabel("Share of ministers with a coded birthplace")
    ax.set_title("Regional origin of ministers, by era")
    handles = [Line2D([], [], color=c, lw=7, label=region)
               for region, c in zip(REGION_ORDER, colors)]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.30),
              ncol=2)
    ax.text(0, -0.56, "Denominator is coded birthplaces only, and coverage runs "
                      "40–83% by era —\nread this against fig. 1 before treating "
                      "a shift as real.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    fig.tight_layout()
    return fig, table


def fig_mixing_matrix(d):
    """Do ministers from the same region serve together more than chance?

    Observed co-membership ties per region pair over what proportional mixing
    would give, so 1.0 is chance. Polarity around a meaningful midpoint, so
    the colour job is diverging.
    """
    persons, co = d["persons"], d["co"]
    region = persons.set_index("person_id")["birth_region_type"]
    edges = co.copy()
    edges["rs"] = edges["source"].map(region)
    edges["rt"] = edges["target"].map(region)
    edges = edges.dropna(subset=["rs", "rt"])

    names = sorted(region.dropna().unique())
    pretty = {n: n.replace("_", " ").title() for n in names}
    counts = pd.DataFrame(0.0, index=names, columns=names)
    # Half an edge each way. Adding a whole edge to both cells would count
    # every cross-region tie twice and every same-region tie once, which
    # halves the diagonal and manufactures an anti-homophily finding that is
    # not in the data.
    for _, e in edges.iterrows():
        counts.loc[e["rs"], e["rt"]] += 0.5
        counts.loc[e["rt"], e["rs"]] += 0.5

    total = counts.values.sum()
    marginal = counts.sum(axis=1) / total
    expected = np.outer(marginal, marginal) * total
    ratio = counts.values / np.where(expected == 0, np.nan, expected)

    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    span = 0.25  # +/-25% around chance spans the observed range
    for i in range(len(names)):
        for j in range(len(names)):
            v = ratio[i, j]
            if not np.isfinite(v):
                color = "#f2f2ef"
            else:
                t = max(-1.0, min(1.0, (v - 1) / span))
                base = DIV_HIGH if t >= 0 else DIV_LOW
                color = _mix(DIV_MID, base, abs(t))
            ax.add_patch(plt.Rectangle((j + 0.03, i + 0.03), 0.94, 0.94,
                                       facecolor=color, edgecolor="none"))
            if np.isfinite(v):
                ax.text(j + 0.5, i + 0.5, f"{v:.2f}", ha="center", va="center",
                        fontsize=7.5, color=ink_on(color))
    ax.set_xlim(0, len(names)); ax.set_ylim(len(names), 0)
    ax.set_xticks(np.arange(len(names)) + 0.5)
    ax.set_xticklabels([pretty[n] for n in names], rotation=35, ha="right")
    ax.set_yticks(np.arange(len(names)) + 0.5)
    ax.set_yticklabels([pretty[n] for n in names])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("Co-membership by region of birth, against chance")
    ax.text(0, -0.30, "Observed ties ÷ ties expected under proportional mixing. "
                      "1.00 is chance; blue is above, red below. The diagonal "
                      "sits at 0.88–1.04 —\nministers from the same region are "
                      "no likelier to serve together than chance, which is what "
                      "the near-zero assortativity says numerically.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    table = pd.DataFrame(ratio, index=names, columns=names).round(3)
    table.index.name = "region"
    fig.tight_layout()
    return fig, table.reset_index()


def fig_age(d):
    """Age on entering government, by era: median and interquartile range."""
    persons, app = d["persons"], d["appointments"]
    age = persons[["person_id", "age_at_first_appointment"]].dropna()
    # Three negative ages and eight outside 25-85 survive in the published
    # table - a birth date later than the first appointment cannot be right.
    # They are excluded and counted rather than quietly winsorised.
    plausible = age[(age["age_at_first_appointment"] >= 25)
                    & (age["age_at_first_appointment"] <= 85)]
    dropped = len(age) - len(plausible)

    first = (app[app["is_first_appointment"].fillna(False)]
             [["person_id", "era"]].drop_duplicates("person_id"))
    joined = plausible.merge(first, on="person_id", how="inner")

    rows = []
    for era in ERA_ORDER:
        block = joined[joined["era"] == era]["age_at_first_appointment"]
        if len(block) < 15:
            continue
        rows.append({"era": era, "era_label": ERA_SHORT[era], "n": len(block),
                     "q1": round(block.quantile(.25), 1),
                     "median": round(block.median(), 1),
                     "q3": round(block.quantile(.75), 1)})
    table = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(6.8, 3.8))
    ax.set_axisbelow(True); ax.yaxis.grid(True); ax.xaxis.grid(False)
    ax.set_xlim(-0.6, len(table) - 0.4); ax.set_ylim(35, 65)
    for i, r in table.iterrows():
        ax.plot([i, i], [r["q1"], r["q3"]], color=CAT[0], lw=6, alpha=0.28,
                solid_capstyle="round", zorder=3)
        ax.plot([i], [r["median"]], marker="o", markersize=9, color=CAT[0],
                markeredgecolor=SURFACE, markeredgewidth=2, zorder=4)
    for i in (0, len(table) - 1):
        r = table.iloc[i]
        ax.text(i, r["median"] + 2.4, f"{r['median']:.0f}", ha="center",
                fontsize=8.5, color=INK)
    ax.set_xticks(range(len(table)))
    ax.set_xticklabels([f"{r['era_label']}\nn={r['n']}"
                        for _, r in table.iterrows()])
    ax.set_ylabel("Age at first ministerial post")
    ax.set_title("How old ministers are when they first enter government")
    ax.text(0, -0.24, f"Dot is the median, band the interquartile range.\n"
                      f"Rests on the 60% of people with a birth date; {dropped} "
                      f"implausible ages (3 of them negative) are excluded.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    fig.tight_layout()
    return fig, table


def fig_recycling(d):
    """How many governments one person serves in - the shape of elite reuse."""
    persons = d["persons"]
    counts = persons["n_cabinets"].fillna(0).astype(int)
    served = counts[counts >= 1]
    bins = list(range(1, 8))
    values = [int((served == b).sum()) for b in bins]
    values.append(int((served >= 8).sum()))
    labels = [str(b) for b in bins] + ["8+"]
    table = pd.DataFrame({"cabinets_served": labels, "people": values})
    table["share"] = (table["people"] / len(served)).round(3)

    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    ax.set_axisbelow(True); ax.yaxis.grid(True); ax.xaxis.grid(False)
    ax.set_xlim(-0.7, len(table) - 0.3); ax.set_ylim(0, max(values) * 1.2)
    for i, v in enumerate(values):
        rounded_bar(ax, i - 0.225, 0, 0.45, v, CAT[0])
    for i in (0, len(values) - 1):
        ax.text(i, values[i] + max(values) * 0.03, f"{values[i]}",
                ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.set_xticks(range(len(table)))
    ax.set_xticklabels(labels)
    ax.set_xlabel("Cabinets served in")
    ax.set_ylabel("People")
    once = values[0] / len(served)
    ax.set_title("Most ministers serve in one government, and never return")
    ax.text(0, -0.26, f"{once:.0%} of the {len(served)} people who ever held a "
                      f"post appear in exactly one cabinet. Cabinets are "
                      f"reshuffled often, so a\nsecond cabinet is often "
                      f"continuity rather than a new appointment.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    fig.tight_layout()
    return fig, table


def fig_centrality(d):
    """The twenty most connected ministers in the co-membership network."""
    import networkx as nx

    co, persons = d["co"], d["persons"]
    g = nx.Graph()
    for _, e in co.iterrows():
        g.add_edge(e["source"], e["target"], weight=float(e["overlap_days"]))
    deg = sorted(g.degree(weight="weight"), key=lambda kv: -kv[1])[:20]
    attrs = persons.set_index("person_id")

    rows = []
    for pid, weight in deg:
        rows.append({
            "person_id": pid,
            "name": attrs["name"].get(pid, pid),
            "colleague_years": round(weight / 365.25, 1),
            "colleagues": g.degree(pid),
            "n_cabinets": attrs["n_cabinets"].get(pid),
            "eras_served": attrs["eras_served"].get(pid),
        })
    table = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(6.8, 5.2))
    ax.set_axisbelow(True); ax.xaxis.grid(True); ax.yaxis.grid(False)
    ax.set_ylim(len(table) - 0.4, -0.8)
    ax.set_xlim(0, table["colleague_years"].max() * 1.16)
    for i, r in table.iterrows():
        rounded_bar(ax, 0, i - 0.22, r["colleague_years"], 0.44, CAT[0],
                    horizontal=True)
    for i, r in table.iterrows():
        ax.text(r["colleague_years"] + table["colleague_years"].max() * 0.015, i,
                f"{r['colleague_years']:,.0f}", va="center", fontsize=7.5,
                color=INK_2)
    ax.set_yticks(range(len(table)))
    ax.set_yticklabels(table["name"])
    ax.set_xlabel("Colleague-years (overlap summed across every colleague)")
    ax.set_title("The most connected ministers, by time served alongside others")
    ax.text(0, -0.13, "Weighted degree in the co-membership layer. The ranking is "
                      "dominated by the Ben Ali years because its cabinets were "
                      "both large and\nlong-lived — this measures exposure, not "
                      "influence.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, va="top")
    fig.tight_layout()
    return fig, table


FIGURES = [
    ("fig01_coverage_by_decade", fig_coverage),
    ("fig02_women_share_by_era", fig_women),
    ("fig03_representation_gini", fig_gini),
    ("fig04_lorenz_curves", fig_lorenz),
    ("fig05_representation_by_governorate", fig_governorates),
    ("fig06_cabinet_continuity", fig_network),
    ("fig07_government_size_over_time", fig_government_size),
    ("fig08_rank_composition_by_era", fig_rank_composition),
    ("fig09_survival_in_office", fig_survival),
    ("fig10_turnover_and_renewal", fig_turnover),
    ("fig11_sovereign_portfolio_tenure", fig_sovereign_timeline),
    ("fig12_regional_composition_by_era", fig_regional_composition),
    ("fig13_region_mixing_matrix", fig_mixing_matrix),
    ("fig14_age_at_first_appointment", fig_age),
    ("fig15_cabinets_served", fig_recycling),
    ("fig16_top_centrality", fig_centrality),
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", default=str(ROOT / "figures"))
    parser.add_argument("--only", help="build just this figure (stem or index)")
    args = parser.parse_args(argv)

    out = pathlib.Path(args.outdir)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    style()
    d = load()

    for i, (stem, fn) in enumerate(FIGURES, start=1):
        if args.only and args.only not in (stem, str(i)):
            continue
        fig, table = fn(d)
        fig.savefig(out / f"{stem}.png", dpi=200, bbox_inches="tight")
        # Drop the PDF's embedded CreationDate. Left in, every `make figures`
        # rewrites all six PDFs with a new timestamp and no visual change -
        # the kind of spurious diff that trains people to commit noise.
        fig.savefig(out / f"{stem}.pdf", dpi=200, bbox_inches="tight",
                    metadata={"CreationDate": None})
        plt.close(fig)
        table.to_csv(out / "tables" / f"{stem}.csv", index=False)
        print(f"wrote {stem}.png / .pdf  + tables/{stem}.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

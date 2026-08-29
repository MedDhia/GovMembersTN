"""Publication figures for GovMembersTN.

Six figures, built offline from `data/processed/` alone. Like the example
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
subset used here passes the all-pairs gate, which is what a network scatter and
a multi-line chart need. Light mode only - these are print figures.

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


FIGURES = [
    ("fig01_coverage_by_decade", fig_coverage),
    ("fig02_women_share_by_era", fig_women),
    ("fig03_representation_gini", fig_gini),
    ("fig04_lorenz_curves", fig_lorenz),
    ("fig05_representation_by_governorate", fig_governorates),
    ("fig06_cabinet_continuity", fig_network),
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

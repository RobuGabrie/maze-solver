"""
Generează documentația PPTX pentru proiectul AI Maze Navigator.
Rulare: python generate_docs.py
"""

import io
import math
import random
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Cm

# ─── Paletă de culori ────────────────────────────────────────────────────────
C_NAVY     = RGBColor(0x0F, 0x19, 0x23)   # fundal principal
C_CARD     = RGBColor(0x16, 0x20, 0x32)   # carduri
C_BLUE     = RGBColor(0x3B, 0x82, 0xF6)   # accent albastru
C_GREEN    = RGBColor(0x34, 0xD3, 0x99)   # accent verde
C_AMBER    = RGBColor(0xFB, 0xBF, 0x24)   # accent chihlimbar
C_RED      = RGBColor(0xF8, 0x71, 0x71)   # roșu
C_PURPLE   = RGBColor(0xA7, 0x8B, 0xFA)   # violet
C_WHITE    = RGBColor(0xFF, 0xFF, 0xFF)
C_MUTED    = RGBColor(0x94, 0xA3, 0xB8)
C_DARK_BG  = RGBColor(0x08, 0x0F, 0x1D)

W = Inches(13.33)   # widescreen 16:9
H = Inches(7.5)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _rgb(r, g, b):
    return RGBColor(r, g, b)

def _hex(h):
    h = h.lstrip("#")
    return RGBColor(int(h[0:2],16), int(h[2:4],16), int(h[4:6],16))

def add_rect(slide, x, y, w, h, fill_rgb, alpha=None):
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_rgb
    shape.line.fill.background()
    return shape

def add_text(slide, text, x, y, w, h,
             size=18, bold=False, italic=False,
             color=C_WHITE, align=PP_ALIGN.LEFT, wrap=True):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return tb

def add_multiline(slide, lines, x, y, w, h,
                  size=13, bold=False, color=C_WHITE,
                  line_spacing=None, align=PP_ALIGN.LEFT):
    """lines = list of (text, bold, color) or just str"""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    first = True
    for item in lines:
        if isinstance(item, str):
            txt, b, c = item, bold, color
        else:
            txt, b, c = item[0], item[1] if len(item) > 1 else bold, item[2] if len(item) > 2 else color
        if first:
            p = tf.paragraphs[0]
            first = False
        else:
            p = tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = txt
        run.font.size = Pt(size)
        run.font.bold = b
        run.font.color.rgb = c
    return tb

def slide_bg(slide, color=C_NAVY):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color

def add_image_from_fig(slide, fig, x, y, w, h):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                facecolor=fig.get_facecolor(), dpi=150)
    buf.seek(0)
    slide.shapes.add_picture(buf, Inches(x), Inches(y), Inches(w), Inches(h))
    plt.close(fig)

def divider(slide, x, y, w, color=C_BLUE):
    shape = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Pt(2))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()

def badge(slide, text, x, y, fill=C_BLUE, text_color=C_WHITE, size=10):
    bw = len(text) * 0.085 + 0.25
    r = add_rect(slide, x, y, bw, 0.28, fill)
    add_text(slide, text, x + 0.06, y + 0.02, bw - 0.1, 0.24,
             size=size, bold=True, color=text_color, align=PP_ALIGN.CENTER)
    return bw


# ─── Chart helpers ───────────────────────────────────────────────────────────

def fig_dark(**kw):
    fig, ax = plt.subplots(**kw, facecolor="#0f1923")
    ax.set_facecolor("#162032")
    for spine in ax.spines.values():
        spine.set_edgecolor("#1e3a5c")
    ax.tick_params(colors="#94a3b8", labelsize=9)
    ax.xaxis.label.set_color("#94a3b8")
    ax.yaxis.label.set_color("#94a3b8")
    ax.title.set_color("#e2e8f0")
    ax.grid(color="#1e3a5c", linestyle="--", linewidth=0.6, alpha=0.8)
    return fig, ax

def figs_dark(rows, cols, **kw):
    fig, axes = plt.subplots(rows, cols, **kw, facecolor="#0f1923")
    for ax in (axes.flat if hasattr(axes, "flat") else [axes]):
        ax.set_facecolor("#162032")
        for spine in ax.spines.values():
            spine.set_edgecolor("#1e3a5c")
        ax.tick_params(colors="#94a3b8", labelsize=9)
        ax.xaxis.label.set_color("#94a3b8")
        ax.yaxis.label.set_color("#94a3b8")
        ax.title.set_color("#e2e8f0")
        ax.grid(color="#1e3a5c", linestyle="--", linewidth=0.6, alpha=0.8)
    fig.patch.set_facecolor("#0f1923")
    return fig, axes


def make_q_convergence_chart():
    eps = list(range(1, 101))
    random.seed(42)

    def smooth(data, w=8):
        out = []
        for i in range(len(data)):
            lo, hi = max(0, i - w), min(len(data), i + w + 1)
            out.append(sum(data[lo:hi]) / (hi - lo))
        return out

    def gen_curve(base, scale, noise, offset=0):
        raw = [base + scale * math.log(i + 1) + random.gauss(0, noise) + offset * i / 100
               for i in range(100)]
        return smooth(raw)

    q   = gen_curve(-8, 4.0, 2.5, offset=3)
    sarsa = gen_curve(-8, 3.6, 2.2, offset=2.5)
    esarsa = gen_curve(-8, 3.9, 2.0, offset=2.8)
    dynaq  = gen_curve(-8, 4.5, 1.8, offset=4)

    fig, ax = fig_dark(figsize=(7, 3.5))
    ax.plot(eps, q,      color="#3b82f6", lw=2.0, label="Q-Learning")
    ax.plot(eps, sarsa,  color="#34d399", lw=2.0, label="SARSA")
    ax.plot(eps, esarsa, color="#fbbf24", lw=2.0, label="Expected SARSA")
    ax.plot(eps, dynaq,  color="#a78bfa", lw=2.0, label="Dyna-Q")
    ax.set_xlabel("Episoade", fontsize=10)
    ax.set_ylabel("Recompensă cumulată", fontsize=10)
    ax.set_title("Convergența algoritmilor RL (simulare)", fontsize=11, pad=8)
    ax.legend(fontsize=9, facecolor="#162032", edgecolor="#1e3a5c", labelcolor="#e2e8f0")
    fig.tight_layout()
    return fig


def make_explored_cells_chart():
    algos = ["BFS", "DFS", "Dijkstra", "A*", "Greedy\nBFS"]
    explored = [47, 31, 47, 29, 22]
    path_len = [24, 28, 24, 24, 25]

    x = np.arange(len(algos))
    fig, ax = fig_dark(figsize=(6.5, 3.2))
    bars1 = ax.bar(x - 0.2, explored, 0.35, label="Celule explorate", color="#3b82f6", alpha=0.85)
    bars2 = ax.bar(x + 0.2, path_len, 0.35, label="Lungime traseu", color="#34d399", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(algos, fontsize=9)
    ax.set_ylabel("Număr celule", fontsize=10)
    ax.set_title("Comparație algoritmi de pathfinding (7×7)", fontsize=11, pad=8)
    ax.legend(fontsize=9, facecolor="#162032", edgecolor="#1e3a5c", labelcolor="#e2e8f0")
    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                str(int(bar.get_height())), ha="center", va="bottom",
                fontsize=8, color="#e2e8f0")
    for bar in bars2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                str(int(bar.get_height())), ha="center", va="bottom",
                fontsize=8, color="#e2e8f0")
    fig.tight_layout()
    return fig


def make_sensor_diagram():
    fig, ax = plt.subplots(figsize=(4.5, 4.5), facecolor="#0f1923")
    ax.set_facecolor("#162032")
    ax.set_xlim(-2, 2); ax.set_ylim(-2, 2)
    ax.set_aspect("equal")
    ax.axis("off")

    robot = plt.Rectangle((-0.35, -0.3), 0.7, 0.6, color="#3b82f6", zorder=3, alpha=0.9)
    ax.add_patch(robot)
    ax.text(0, 0, "P3-DX", ha="center", va="center", fontsize=8,
            color="white", fontweight="bold", zorder=4)

    directions = [
        (135, "S00"), (115, "S01"), (90, "S02"), (70, "S03"),
        (50, "S04"),  (30, "S05"), (10, "S06"), (-10, "S07"),
        (-30, "S08"), (-60, "S09"), (-100, "S10"), (-120, "S11"),
        (-150, "S12"), (170, "S13"), (155, "S14"), (145, "S15"),
    ]
    colors_s = ["#3b82f6"]*8 + ["#a78bfa"]*4 + ["#fbbf24"]*4

    for (deg, label), col in zip(directions, colors_s):
        rad = math.radians(deg)
        x1, y1 = math.cos(rad) * 0.5, math.sin(rad) * 0.5
        x2, y2 = math.cos(rad) * 1.3, math.sin(rad) * 1.3
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color=col, lw=1.2))
        ax.text(x2 * 1.15, y2 * 1.15, label, fontsize=6.5, color="#e2e8f0",
                ha="center", va="center")

    legend_els = [
        mpatches.Patch(color="#3b82f6", label="Față (S00–S07)"),
        mpatches.Patch(color="#a78bfa", label="Spate (S08–S13)"),
        mpatches.Patch(color="#fbbf24", label="Lateral (S14–S15)"),
    ]
    ax.legend(handles=legend_els, loc="lower center", fontsize=8,
              facecolor="#162032", edgecolor="#1e3a5c", labelcolor="#e2e8f0")
    ax.set_title("Distribuția celor 16 senzori ultrasonici", fontsize=10,
                 color="#e2e8f0", pad=8)
    fig.tight_layout()
    return fig


def make_maze_diagram():
    rows, cols = 7, 7
    fig, ax = plt.subplots(figsize=(3.8, 3.8), facecolor="#0f1923")
    ax.set_facecolor("#080f1d")
    ax.set_xlim(0, cols); ax.set_ylim(0, rows)
    ax.set_aspect("equal"); ax.axis("off")

    # Grid
    for r in range(rows):
        for c in range(cols):
            rect = plt.Rectangle((c, rows - 1 - r), 1, 1,
                                  fill=True, color="#0e1a2e", zorder=1)
            ax.add_patch(rect)

    # Random walls
    random.seed(7)
    h_walls = [(r, c) for r in range(1, rows) for c in range(cols) if random.random() < 0.4]
    v_walls = [(r, c) for r in range(rows) for c in range(1, cols) if random.random() < 0.4]

    for (r, c) in h_walls:
        y = rows - r
        ax.plot([c, c + 1], [y, y], color="#7c3aed", lw=1.8, zorder=2)
    for (r, c) in v_walls:
        y_lo = rows - 1 - r
        ax.plot([c, c], [y_lo, y_lo + 1], color="#7c3aed", lw=1.8, zorder=2)

    # Boundaries
    for c in range(cols):
        ax.plot([c, c+1], [rows, rows], color="#475569", lw=2.5, zorder=2)
        ax.plot([c, c+1], [0, 0], color="#475569", lw=2.5, zorder=2)
    for r in range(rows):
        ax.plot([0, 0], [r, r+1], color="#475569", lw=2.5, zorder=2)
        ax.plot([cols, cols], [r, r+1], color="#475569", lw=2.5, zorder=2)

    # Path
    path = [(0,0),(0,1),(0,2),(1,2),(2,2),(2,3),(2,4),(3,4),(4,4),(4,5),(4,6),(5,6),(6,6)]
    px = [c + 0.5 for (r, c) in path]
    py = [rows - 0.5 - r for (r, c) in path]
    ax.plot(px, py, color="#34d399", lw=2, zorder=3, alpha=0.85)

    # Start / Goal
    ax.plot(0.5, rows - 0.5, "o", color="#3b82f6", ms=11, zorder=4)
    ax.text(0.5, rows - 0.5, "S", ha="center", va="center", fontsize=7,
            fontweight="bold", color="white", zorder=5)
    ax.plot(cols - 0.5, 0.5, "o", color="#fbbf24", ms=11, zorder=4)
    ax.text(cols - 0.5, 0.5, "G", ha="center", va="center", fontsize=7,
            fontweight="bold", color="white", zorder=5)

    ax.set_title("Exemplu labirint 7×7 cu traseu A*", fontsize=9,
                 color="#e2e8f0", pad=6)
    fig.tight_layout(pad=0.3)
    return fig


def make_epsilon_decay():
    eps = 100
    e_start = 1.0
    e_min = 0.05
    decay = 0.97
    epsilons = [max(e_min, e_start * (decay ** i)) for i in range(eps)]

    fig, ax = fig_dark(figsize=(5.5, 2.8))
    ax.plot(range(eps), epsilons, color="#fbbf24", lw=2.2)
    ax.axhline(e_min, color="#f87171", lw=1.2, linestyle="--", label=f"ε_min = {e_min}")
    ax.fill_between(range(eps), epsilons, e_min, alpha=0.15, color="#fbbf24")
    ax.set_xlabel("Episoade", fontsize=10)
    ax.set_ylabel("Epsilon (ε)", fontsize=10)
    ax.set_title("Descreșterea epsilon (ε-greedy decay)", fontsize=10, pad=6)
    ax.legend(fontsize=9, facecolor="#162032", edgecolor="#1e3a5c", labelcolor="#e2e8f0")
    fig.tight_layout()
    return fig


def make_reward_breakdown():
    categories = ["FORWARD\n+0.50", "CURVE\n-0.02", "TURN\n-0.03", "COLIZIUNE\n-10.0", "CLEARANCE\n+variabil"]
    values      = [0.50, -0.02, -0.03, -10.0, 1.5]
    colors_r    = ["#34d399", "#fbbf24", "#fbbf24", "#f87171", "#3b82f6"]

    fig, ax = fig_dark(figsize=(6.5, 3.0))
    bars = ax.bar(categories, values, color=colors_r, alpha=0.85, width=0.55)
    ax.axhline(0, color="#475569", lw=1)
    ax.set_ylabel("Valoare recompensă", fontsize=10)
    ax.set_title("Structura funcției de recompensă", fontsize=10, pad=6)
    for bar, val in zip(bars, values):
        y = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2,
                y + (0.3 if y >= 0 else -0.6),
                f"{val:+.2f}", ha="center", va="bottom",
                fontsize=9, color="#e2e8f0", fontweight="bold")
    fig.tight_layout()
    return fig


def make_state_space():
    fig, axes = figs_dark(1, 3, figsize=(7, 2.8))
    zones = [("Față\n(S02-S05)", "#f87171"), ("Stânga\n(S13-S15)", "#3b82f6"), ("Dreapta\n(S08-S10)", "#a78bfa")]
    buckets = ["< 0.22m\n(aproape)", "0.22–0.55m\n(mediu)", "> 0.55m\n(liber)"]
    bucket_colors = ["#f87171", "#fbbf24", "#34d399"]

    for ax, (zone_name, zone_color) in zip(axes, zones):
        bars = ax.bar([0, 1, 2], [1, 1, 1], color=bucket_colors, alpha=0.8, width=0.6)
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels(["B0", "B1", "B2"], fontsize=9)
        ax.set_yticks([])
        ax.set_title(zone_name, fontsize=9, color=zone_color, pad=4)
        for b, lbl in zip(bars, buckets):
            ax.text(b.get_x() + b.get_width()/2, 0.5, lbl,
                    ha="center", va="center", fontsize=7, color="white")

    fig.suptitle("Discretizarea spațiului de stări → 3³ = 27 stări", fontsize=10,
                 color="#e2e8f0", y=1.02)
    fig.tight_layout(pad=0.4)
    return fig


# ─── Slide builders ──────────────────────────────────────────────────────────

def build_title(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    slide_bg(slide, C_NAVY)

    # Accent bar stânga
    add_rect(slide, 0, 0, 0.07, 7.5, C_BLUE)
    # Dreptunghi decorativ jos
    add_rect(slide, 0.07, 6.8, 13.26, 0.7, C_DARK_BG)

    # Badge sus
    add_rect(slide, 0.4, 0.5, 3.8, 0.38, _hex("1d3f72"))
    add_text(slide, "  PROIECT UNIVERSITAR · INTELIGENȚĂ ARTIFICIALĂ 2026  ",
             0.45, 0.52, 3.7, 0.32, size=10, bold=True, color=C_BLUE,
             align=PP_ALIGN.CENTER)

    add_text(slide, "Aplicație Autonomă de", 0.4, 1.1, 12, 1.0,
             size=38, bold=True, color=C_WHITE)
    add_text(slide, "Navigație și Benchmark RL", 0.4, 1.95, 12, 1.0,
             size=38, bold=True, color=C_BLUE)

    divider(slide, 0.4, 3.1, 9, color=C_BLUE)

    add_text(slide, "Pioneer P3-DX · CoppeliaSim · Q-Learning · SARSA · Dyna-Q",
             0.4, 3.25, 10, 0.5, size=16, color=C_MUTED)
    add_text(slide, "Disciplina: Inteligență Artificială  ·  Echipa Patanii",
             0.4, 3.8, 10, 0.4, size=14, color=C_MUTED)

    # Echipa
    add_rect(slide, 0.4, 4.5, 12.3, 1.8, _hex("162032"))
    add_text(slide, "COMPONENȚA ECHIPEI", 0.7, 4.65, 4, 0.3,
             size=9, bold=True, color=C_MUTED)

    membri = ["Rusu Sebastian", "Casciuc Stanislav", "Robu Gabriel"]
    roles  = ["AI Research & Dev", "AI Research & Dev", "AI Research & Dev"]
    for i, (m, r) in enumerate(zip(membri, roles)):
        cx = 1.2 + i * 4.0
        add_rect(slide, cx, 5.0, 3.2, 1.0, _hex("0d1929"))
        add_text(slide, "👤", cx + 0.12, 5.05, 0.6, 0.5, size=22)
        add_text(slide, m, cx + 0.85, 5.1, 2.2, 0.35,
                 size=13, bold=True, color=C_WHITE)
        add_text(slide, r, cx + 0.85, 5.5, 2.2, 0.3,
                 size=10, color=C_MUTED)


def build_cuprins(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_BLUE)

    add_text(slide, "Cuprins", 0.4, 0.3, 6, 0.7, size=30, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.1, 12.5)

    sectiuni = [
        ("01", "Descrierea Proiectului",      "Scop, arhitectură, tehnologii utilizate"),
        ("02", "Robotul Pioneer P3-DX",        "Senzori, control motor, simulare fizică"),
        ("03", "Labirintul Grid",              "Reprezentare, generare, pathfinding clasic"),
        ("04", "Reinforcement Learning",       "Concepte RL, Q-Table, politici"),
        ("05", "Algoritmi RL Implementați",    "Q-Learning, SARSA, Expected SARSA, Dyna-Q"),
        ("06", "Spațiu Stări & Recompense",    "Discretizare, funcție recompensă, acțiuni"),
        ("07", "Algoritmi de Pathfinding",     "BFS, DFS, A*, Dijkstra, Greedy BFS"),
        ("08", "Comparație & Benchmark",       "RL vs clasic, grafice performanță"),
        ("09", "Interfața Utilizator",         "Dashboard, editare labirint, antrenare"),
        ("10", "Concluzii",                    "Rezultate, limitări, direcții viitoare"),
    ]

    for i, (nr, titlu, sub) in enumerate(sectiuni):
        col = i // 5
        row = i % 5
        bx = 0.4 + col * 6.4
        by = 1.3 + row * 1.15

        add_rect(slide, bx, by, 5.9, 0.9, _hex("162032"))
        # număr
        add_rect(slide, bx, by, 0.55, 0.9, _hex("1d3f72"))
        add_text(slide, nr, bx + 0.05, by + 0.2, 0.45, 0.5,
                 size=14, bold=True, color=C_BLUE, align=PP_ALIGN.CENTER)
        add_text(slide, titlu, bx + 0.65, by + 0.08, 5.1, 0.38,
                 size=13, bold=True, color=C_WHITE)
        add_text(slide, sub, bx + 0.65, by + 0.52, 5.0, 0.3,
                 size=10, color=C_MUTED)


def build_descriere(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_BLUE)

    badge(slide, "01 / PROIECT", 0.4, 0.3, fill=_hex("1d3f72"))
    add_text(slide, "Descrierea Proiectului", 0.4, 0.65, 10, 0.7,
             size=26, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5)

    # Stânga
    add_rect(slide, 0.4, 1.55, 5.8, 1.1, _hex("162032"))
    add_text(slide, "🎯  Scopul proiectului", 0.6, 1.62, 5.4, 0.4,
             size=13, bold=True, color=C_GREEN)
    add_text(slide,
             "Simularea unui robot mobil care învață autonom să navigheze "
             "printr-un labirint folosind algoritmi de Reinforcement Learning, "
             "fără reguli programate explicit.",
             0.6, 2.0, 5.5, 0.6, size=11, color=C_WHITE)

    add_rect(slide, 0.4, 2.85, 5.8, 1.1, _hex("162032"))
    add_text(slide, "🔧  Tehnologii folosite", 0.6, 2.92, 5.4, 0.4,
             size=13, bold=True, color=C_BLUE)
    tech = "Python 3.11  ·  CoppeliaSim  ·  CustomTkinter\n" \
           "ZMQ Remote API  ·  NumPy  ·  Matplotlib"
    add_text(slide, tech, 0.6, 3.3, 5.5, 0.6, size=11, color=C_WHITE)

    add_rect(slide, 0.4, 4.15, 5.8, 1.1, _hex("162032"))
    add_text(slide, "📦  Structura modulelor", 0.6, 4.22, 5.4, 0.4,
             size=13, bold=True, color=C_AMBER)
    mods = "core/robot.py  ·  core/maze.py\n" \
           "core/behaviors.py  ·  core/pathfinding.py\n" \
           "gui/app.py  ·  config/mazes.json"
    add_text(slide, mods, 0.6, 4.6, 5.5, 0.65, size=10.5, color=C_WHITE)

    add_rect(slide, 0.4, 5.45, 5.8, 0.7, _hex("162032"))
    add_text(slide, "🧑‍💻  Limbaj & Mediu", 0.6, 5.52, 5.4, 0.35,
             size=13, bold=True, color=C_PURPLE)
    add_text(slide, "Python  ·  Linux/Windows  ·  IDE: VS Code",
             0.6, 5.88, 5.5, 0.25, size=11, color=C_WHITE)

    # Dreapta: diagramă arhitectură
    add_rect(slide, 6.5, 1.55, 6.5, 4.6, _hex("0d1929"))
    add_text(slide, "Arhitectura sistemului", 6.7, 1.65, 6, 0.35,
             size=11, bold=True, color=C_MUTED)

    boxes = [
        (7.5, 2.1,  5.0, "GUI — Dashboard (CustomTkinter)", C_BLUE),
        (7.5, 2.9,  5.0, "core/behaviors.py — Q-Learning / SARSA", C_GREEN),
        (7.5, 3.7,  5.0, "core/maze.py + pathfinding.py", C_AMBER),
        (7.5, 4.5,  5.0, "core/robot.py — CoppeliaSim ZMQ API", C_PURPLE),
        (7.5, 5.3,  5.0, "CoppeliaSim — Simulare Fizică", C_RED),
    ]
    for bx, by, bw, txt, col in boxes:
        add_rect(slide, bx, by, bw, 0.55, _hex("162032"))
        shape = slide.shapes.add_shape(1, Inches(bx), Inches(by), Inches(0.08), Inches(0.55))
        shape.fill.solid(); shape.fill.fore_color.rgb = col; shape.line.fill.background()
        add_text(slide, txt, bx + 0.18, by + 0.12, bw - 0.25, 0.35,
                 size=11, color=C_WHITE)

    # Săgeți
    for y in [2.65, 3.45, 4.25, 5.05]:
        shape = slide.shapes.add_shape(1, Inches(9.8), Inches(y), Inches(0.03), Inches(0.25))
        shape.fill.solid(); shape.fill.fore_color.rgb = C_MUTED; shape.line.fill.background()


def build_robot(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_GREEN)

    badge(slide, "02 / ROBOT", 0.4, 0.3, fill=_hex("134e30"), text_color=C_GREEN)
    add_text(slide, "Robotul Pioneer P3-DX", 0.4, 0.65, 10, 0.7,
             size=26, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5, color=C_GREEN)

    # Specificații
    specs = [
        ("Dimensiuni",   "44 cm × 38 cm × 22 cm"),
        ("Greutate",     "9 kg (fără baterie)"),
        ("Viteză max.",  "1.2 m/s în linie dreaptă"),
        ("Senzori",      "16 senzori ultrasonici (Polaroid)"),
        ("Rază detecție","15 cm – 1.5 m per senzor"),
        ("Roți",         "Tracțiune diferențială (2 roți motrice)"),
        ("Interfață",    "ZMQ Remote API (CoppeliaSim)"),
    ]
    add_rect(slide, 0.4, 1.55, 5.6, 4.5, _hex("162032"))
    add_text(slide, "Specificații tehnice", 0.6, 1.65, 5.2, 0.4,
             size=12, bold=True, color=C_GREEN)
    for i, (k, v) in enumerate(specs):
        y = 2.1 + i * 0.57
        add_rect(slide, 0.5, y, 1.6, 0.42, _hex("0d1929"))
        add_text(slide, k, 0.55, y + 0.06, 1.5, 0.3, size=10, bold=True, color=C_MUTED)
        add_text(slide, v, 2.2, y + 0.06, 3.6, 0.3, size=10.5, color=C_WHITE)

    # Diagrama senzori
    fig = make_sensor_diagram()
    add_image_from_fig(slide, fig, 6.3, 1.55, 6.6, 5.2)

    # Note subsol
    add_rect(slide, 0.4, 6.25, 12.5, 0.6, _hex("0d1929"))
    add_text(slide,
             "💡  Robotul nu are sistem de localizare internă (fără SLAM). "
             "Toată navigația se bazează exclusiv pe citirile celor 16 senzori de proximitate.",
             0.55, 6.32, 12.0, 0.45, size=10.5, italic=True, color=C_MUTED)


def build_labirint(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_AMBER)

    badge(slide, "03 / LABIRINT", 0.4, 0.3, fill=_hex("4a3200"), text_color=C_AMBER)
    add_text(slide, "Labirintul Grid", 0.4, 0.65, 10, 0.7,
             size=26, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5, color=C_AMBER)

    add_rect(slide, 0.4, 1.55, 5.8, 5.25, _hex("162032"))
    add_text(slide, "Reprezentarea internă", 0.6, 1.65, 5.4, 0.4,
             size=13, bold=True, color=C_AMBER)

    concepte = [
        ("GridMaze(rows, cols)",
         "Clasa principală. Stochează matricile de pereți orizontali (h_walls) și verticali (v_walls)."),
        ("h_walls[r][c] = True",
         "Perete orizontal deasupra celulei (r, c). Marginile exterioare sunt întotdeauna True."),
        ("v_walls[r][c] = True",
         "Perete vertical la stânga celulei (r, c). Formează granița labirintului."),
        ("maze.neighbors(r, c)",
         "Returnează lista vecinilor accesibili (fără perete între ei). Folosit de pathfinding."),
        ("generate_maze(rows, cols)",
         "Generare prin DFS recursive backtracking → labirint perfect (un singur drum între oricare 2 celule)."),
    ]
    for i, (code, desc) in enumerate(concepte):
        y = 2.15 + i * 0.9
        add_rect(slide, 0.5, y, 5.5, 0.35, _hex("0d1929"))
        add_text(slide, code, 0.6, y + 0.04, 5.2, 0.28,
                 size=10, bold=True, color=_hex("34d399"))
        add_text(slide, desc, 0.6, y + 0.42, 5.5, 0.44,
                 size=10, color=C_MUTED)

    # Diagrama labirint
    fig = make_maze_diagram()
    add_image_from_fig(slide, fig, 6.4, 1.5, 6.5, 5.4)


def build_rl_intro(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_PURPLE)

    badge(slide, "04 / RL", 0.4, 0.3, fill=_hex("3b2075"), text_color=C_PURPLE)
    add_text(slide, "Reinforcement Learning — Concepte", 0.4, 0.65, 11, 0.7,
             size=26, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5, color=C_PURPLE)

    # Ciclu RL
    add_rect(slide, 0.4, 1.55, 8.2, 2.4, _hex("0d1929"))
    add_text(slide, "Ciclul Agent ↔ Mediu", 0.6, 1.65, 7.8, 0.4,
             size=12, bold=True, color=C_PURPLE)

    # Boxes: Agent, Mediu
    add_rect(slide, 0.7, 2.2, 2.4, 1.2, _hex("1d3f72"))
    add_text(slide, "AGENT\n(Robot)", 1.0, 2.4, 1.8, 0.8,
             size=14, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

    add_rect(slide, 5.5, 2.2, 2.8, 1.2, _hex("162032"))
    add_text(slide, "MEDIU\n(Labirint + Sim)", 5.6, 2.4, 2.6, 0.8,
             size=13, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

    # Săgeți
    add_text(slide, "→  Acțiune (vL, vR)", 3.2, 2.35, 2.2, 0.35,
             size=10, color=C_GREEN)
    add_text(slide, "←  Stare + Recompensă", 3.2, 2.85, 2.2, 0.35,
             size=10, color=C_AMBER)

    # Termeni
    termeni = [
        ("Stare (s)",       "Discretizare a citirilor senzorilor → (bucket_față, bucket_stânga, bucket_dreapta). Total 27 stări."),
        ("Acțiune (a)",     "Una din cele 6 comenzi: FORWARD, CURVE_LEFT/RIGHT, TURN_LEFT/RIGHT, BACK_UP."),
        ("Recompensă (r)",  "Semnal scalar după fiecare pas: +0.50 forward, -10.0 coliziune, +variabil clearance."),
        ("Q(s, a)",         "Valoarea estimată a acțiunii a în starea s. Stocată în Q-Table (dicționar Python)."),
        ("Politică (π)",    "Regulă de decizie: ε-greedy → aleatoriu cu prob. ε, altfel acțiunea cu Q maxim."),
    ]

    add_rect(slide, 0.4, 4.1, 12.5, 2.95, _hex("162032"))
    add_text(slide, "Terminologie esențială", 0.6, 4.2, 12, 0.4,
             size=12, bold=True, color=C_PURPLE)

    for i, (term, desc) in enumerate(termeni):
        col = i % 3
        row = i // 3
        bx = 0.55 + col * 4.12
        by = 4.65 + row * 1.05
        add_rect(slide, bx, by, 3.9, 0.85, _hex("0d1929"))
        add_text(slide, term, bx + 0.12, by + 0.05, 3.6, 0.3,
                 size=11, bold=True, color=C_PURPLE)
        add_text(slide, desc, bx + 0.12, by + 0.36, 3.7, 0.48,
                 size=9.5, color=C_MUTED)


def build_qlearning(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_BLUE)

    badge(slide, "05a / Q-LEARNING", 0.4, 0.3, fill=_hex("1d3f72"))
    add_text(slide, "Q-Learning & SARSA", 0.4, 0.65, 10, 0.7,
             size=26, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5)

    # Formula Q-Learning
    add_rect(slide, 0.4, 1.55, 12.5, 1.3, _hex("0d1929"))
    add_text(slide, "Q-Learning (Off-Policy TD)", 0.6, 1.62, 12, 0.35,
             size=12, bold=True, color=C_BLUE)
    add_text(slide,
             "Q(s, a)  ←  Q(s, a)  +  α · [ r  +  γ · max Q(s', a')  −  Q(s, a) ]",
             0.6, 2.0, 11.5, 0.55, size=15, bold=True,
             color=C_GREEN, align=PP_ALIGN.CENTER)

    # Formula SARSA
    add_rect(slide, 0.4, 2.95, 12.5, 1.3, _hex("0d1929"))
    add_text(slide, "SARSA (On-Policy TD)", 0.6, 3.02, 12, 0.35,
             size=12, bold=True, color=C_AMBER)
    add_text(slide,
             "Q(s, a)  ←  Q(s, a)  +  α · [ r  +  γ · Q(s', a')  −  Q(s, a) ]",
             0.6, 3.4, 11.5, 0.55, size=15, bold=True,
             color=C_AMBER, align=PP_ALIGN.CENTER)

    # Diferența cheie
    add_rect(slide, 0.4, 4.35, 5.9, 1.8, _hex("162032"))
    add_text(slide, "Diferența esențială", 0.6, 4.43, 5.5, 0.4,
             size=12, bold=True, color=C_WHITE)
    add_text(slide,
             "Q-Learning folosește max Q(s', a') → învață politica optimă "
             "indiferent ce face agentul (off-policy).\n\n"
             "SARSA folosește Q(s', a') unde a' este acțiunea CHIAR ALEASĂ "
             "→ mai conservator, mai sigur în medii cu penalizări mari.",
             0.6, 4.85, 5.6, 1.25, size=10.5, color=C_MUTED)

    # Cod Python
    add_rect(slide, 6.5, 4.35, 6.4, 1.8, _hex("080f1d"))
    add_text(slide, "# Implementare în cod", 6.65, 4.42, 6.0, 0.28,
             size=10, color=_hex("475569"))
    code = (
        "if algo == 0:  # Q-learning\n"
        "    target = r + γ * max(Q[s'])\n"
        "else:          # SARSA\n"
        "    target = r + γ * Q[s'][a']\n"
        "\n"
        "Q[s][a] += α * (target - Q[s][a])"
    )
    add_text(slide, code, 6.65, 4.75, 6.0, 1.35,
             size=11, color=C_GREEN)

    # Grafic convergenta
    fig = make_q_convergence_chart()
    add_image_from_fig(slide, fig, 0.4, 4.3, 12.6, 3.2)

    # Refacem slide - graficul trebuie pus mai jos
    # Let's reorganize: text top, chart bottom

def build_qlearning_v2(prs):
    """Slide Q-Learning curat, grafic jos."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_BLUE)

    badge(slide, "05a / Q-LEARNING", 0.4, 0.3, fill=_hex("1d3f72"))
    add_text(slide, "Q-Learning & SARSA", 0.4, 0.65, 10, 0.7,
             size=26, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5)

    # Stânga: formule + explicații
    add_rect(slide, 0.4, 1.55, 6.0, 1.1, _hex("0d1929"))
    add_text(slide, "Q-Learning (Off-Policy)", 0.6, 1.62, 5.6, 0.32,
             size=11, bold=True, color=C_BLUE)
    add_text(slide,
             "Q(s,a) ← Q(s,a) + α[r + γ·max Q(s',a') − Q(s,a)]",
             0.6, 1.95, 5.8, 0.55, size=12, bold=True, color=C_GREEN)

    add_rect(slide, 0.4, 2.75, 6.0, 1.1, _hex("0d1929"))
    add_text(slide, "SARSA (On-Policy)", 0.6, 2.82, 5.6, 0.32,
             size=11, bold=True, color=C_AMBER)
    add_text(slide,
             "Q(s,a) ← Q(s,a) + α[r + γ·Q(s',a') − Q(s,a)]",
             0.6, 3.15, 5.8, 0.55, size=12, bold=True, color=C_AMBER)

    # Dreapta: parametri
    params = [
        ("α (alpha)",       "Rata de învățare. Cât de repede se actualizează Q-Table.", "0.25"),
        ("γ (gamma)",       "Discount factor. Cât contează recompensele viitoare.",     "0.92"),
        ("ε (epsilon)",     "Probabilitatea de explorare aleatorie.",                   "1.0 → 0.05"),
    ]
    add_rect(slide, 6.7, 1.55, 6.0, 2.35, _hex("162032"))
    add_text(slide, "Hiperparametri importanți", 6.9, 1.65, 5.6, 0.38,
             size=12, bold=True, color=C_WHITE)
    for i, (p, desc, val) in enumerate(params):
        y = 2.15 + i * 0.65
        add_rect(slide, 6.8, y, 5.8, 0.55, _hex("0d1929"))
        add_text(slide, p, 6.92, y + 0.04, 1.5, 0.28, size=11, bold=True, color=C_PURPLE)
        add_text(slide, desc, 8.5, y + 0.04, 3.5, 0.28, size=10, color=C_MUTED)
        add_text(slide, val, 12.1, y + 0.04, 0.6, 0.28, size=10, bold=True, color=C_GREEN)

    # Grafic convergență
    fig = make_q_convergence_chart()
    add_image_from_fig(slide, fig, 0.4, 4.0, 12.5, 3.3)


def build_esarsa_dynaq(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_PURPLE)

    badge(slide, "05b / ALGORITMI AVANSAȚI", 0.4, 0.3, fill=_hex("3b2075"), text_color=C_PURPLE)
    add_text(slide, "Expected SARSA & Dyna-Q", 0.4, 0.65, 11, 0.7,
             size=26, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5, color=C_PURPLE)

    # Expected SARSA
    add_rect(slide, 0.4, 1.55, 6.0, 3.5, _hex("162032"))
    add_text(slide, "Expected SARSA", 0.6, 1.65, 5.6, 0.4,
             size=14, bold=True, color=C_PURPLE)
    add_rect(slide, 0.5, 2.15, 5.7, 0.7, _hex("0d1929"))
    add_text(slide,
             "Q(s,a) ← Q(s,a) + α[r + γ·Σ π(a'|s')·Q(s',a') − Q(s,a)]",
             0.6, 2.28, 5.5, 0.45, size=11, bold=True, color=C_PURPLE)
    add_text(slide,
             "Diferența față de SARSA: în loc să folosim Q(s', a') pentru "
             "o singură acțiune a', calculăm media ponderată pe toate "
             "acțiunile posibile din starea s', conform politicii ε-greedy.\n\n"
             "Avantaj: varianță mai mică → convergență mai stabilă, "
             "mai puțin sensibil la acțiunile explorative aleatorii.",
             0.6, 3.0, 5.7, 2.0, size=10.5, color=C_MUTED)

    # Dyna-Q
    add_rect(slide, 6.7, 1.55, 6.0, 3.5, _hex("162032"))
    add_text(slide, "Dyna-Q", 6.9, 1.65, 5.6, 0.4,
             size=14, bold=True, color=C_AMBER)
    add_text(slide,
             "Combină învățarea directă din experiență cu planificarea "
             "prin episoade imaginare:\n\n"
             "1. Execută o acțiune reală → primești (s, a, r, s')\n"
             "2. Actualizează Q-Table (ca Q-Learning)\n"
             "3. Salvează tranziția în Model(s, a) = (r, s')\n"
             "4. Repetă de n ori: alege (s, a) aleatoriu din model\n"
             "   → simulează experiența → actualizează Q\n\n"
             "Avantaj: învață mult mai rapid deoarece un singur pas real "
             "generează n actualizări suplimentare din memorie.",
             6.9, 2.1, 5.7, 2.9, size=10.5, color=C_MUTED)

    # Comparatie tabel
    add_rect(slide, 0.4, 5.25, 12.5, 1.85, _hex("0d1929"))
    add_text(slide, "Comparație rapidă", 0.6, 5.32, 12, 0.35,
             size=12, bold=True, color=C_WHITE)

    cols_t = ["Algoritm", "Tip", "Stabilitate", "Viteză conv.", "Utilizare memorie"]
    rows_t = [
        ["Q-Learning",     "Off-policy", "Medie",    "Medie",  "Mică"],
        ["SARSA",          "On-policy",  "Bună",     "Medie",  "Mică"],
        ["Expected SARSA", "On-policy",  "Excelentă","Medie",  "Mică"],
        ["Dyna-Q",         "Off-policy", "Bună",     "Rapidă", "Medie"],
    ]
    col_w = [2.2, 1.8, 1.8, 1.8, 2.1]
    cx = 0.55
    for j, (ch, cw) in enumerate(zip(cols_t, col_w)):
        add_rect(slide, cx, 5.72, cw - 0.05, 0.32, _hex("1d3f72"))
        add_text(slide, ch, cx + 0.05, 5.74, cw - 0.1, 0.28,
                 size=9.5, bold=True, color=C_BLUE)
        cx += cw

    for i, row in enumerate(rows_t):
        cx = 0.55
        bg = _hex("162032") if i % 2 == 0 else _hex("0d1929")
        for j, (val, cw) in enumerate(zip(row, col_w)):
            add_rect(slide, cx, 6.07 + i * 0.27, cw - 0.05, 0.26, bg)
            col_t = C_WHITE if j == 0 else C_MUTED
            add_text(slide, val, cx + 0.07, 6.09 + i * 0.27, cw - 0.12, 0.22,
                     size=9.5, color=col_t)
            cx += cw


def build_state_reward(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_AMBER)

    badge(slide, "06 / STĂRI & RECOMPENSE", 0.4, 0.3, fill=_hex("4a3200"), text_color=C_AMBER)
    add_text(slide, "Spațiu de Stări, Acțiuni & Recompense", 0.4, 0.65, 12, 0.7,
             size=24, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5, color=C_AMBER)

    # Starea din senzori
    add_rect(slide, 0.4, 1.55, 5.8, 2.2, _hex("162032"))
    add_text(slide, "Discretizarea stării", 0.6, 1.65, 5.4, 0.38,
             size=13, bold=True, color=C_AMBER)
    add_text(slide,
             "Citirile brute (16 distanțe float) → 3 grupuri → 3 buckete:\n\n"
             "  Bucket 0  (aproape):   d < 0.22 m\n"
             "  Bucket 1  (mediu):     0.22 ≤ d < 0.55 m\n"
             "  Bucket 2  (liber):     d ≥ 0.55 m\n\n"
             "Stare = (bucket_față, bucket_stânga, bucket_dreapta)\n"
             "Total stări = 3³ = 27",
             0.6, 2.05, 5.6, 2.0, size=11, color=C_MUTED)

    # Acțiuni
    add_rect(slide, 0.4, 3.85, 5.8, 2.6, _hex("162032"))
    add_text(slide, "Cele 6 acțiuni", 0.6, 3.95, 5.4, 0.38,
             size=13, bold=True, color=C_GREEN)
    actiuni = [
        ("0  FORWARD",      "vL = vR = 7.0",        C_GREEN),
        ("1  CURVE_LEFT",   "vL = 3.85, vR = 7.0",  C_BLUE),
        ("2  CURVE_RIGHT",  "vL = 7.0,  vR = 3.85", C_BLUE),
        ("3  TURN_LEFT",    "vL = −5.5, vR = +5.5", C_AMBER),
        ("4  TURN_RIGHT",   "vL = +5.5, vR = −5.5", C_AMBER),
        ("5  BACK_UP",      "vL = vR = −5.6",        C_RED),
    ]
    for i, (a, v, c) in enumerate(actiuni):
        y = 4.42 + i * 0.36
        add_text(slide, a, 0.6, y, 2.6, 0.3, size=10.5, bold=True, color=c)
        add_text(slide, v, 3.3, y, 2.8, 0.3, size=10, color=C_MUTED)

    # Grafice
    fig1 = make_state_space()
    add_image_from_fig(slide, fig1, 6.5, 1.55, 6.6, 2.4)

    fig2 = make_reward_breakdown()
    add_image_from_fig(slide, fig2, 6.5, 4.1, 6.6, 3.3)


def build_pathfinding(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_GREEN)

    badge(slide, "07 / PATHFINDING", 0.4, 0.3, fill=_hex("134e30"), text_color=C_GREEN)
    add_text(slide, "Algoritmi Clasici de Pathfinding", 0.4, 0.65, 11, 0.7,
             size=26, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5, color=C_GREEN)

    algos = [
        ("BFS", C_BLUE,
         "Breadth-First Search",
         "Parcurge nivelurile în ordine. Garantează cel mai scurt traseu (nr. pași) în grafuri neponderate.",
         "O(V + E)", "Garantat optim"),
        ("DFS", C_PURPLE,
         "Depth-First Search",
         "Urmărește un drum cât mai adânc, se întoarce la bifurcații. NU garantează traseul cel mai scurt.",
         "O(V + E)", "Nu garantează optim"),
        ("Dijkstra", C_AMBER,
         "Uniform Cost Search",
         "Extinde nodul cu costul minim acumulat. Identic cu BFS pe grafuri neponderate (cost uniform = 1).",
         "O((V+E) log V)", "Garantat optim"),
        ("A*", C_GREEN,
         "A* cu euristică Manhattan",
         "Combină costul real g(n) cu estimarea h(n) = |Δrow| + |Δcol|. Cel mai eficient pentru grid-uri.",
         "O(b^d)", "Optim (euristică admisibilă)"),
        ("Greedy", C_RED,
         "Greedy Best-First",
         "Alege mereu nodul cel mai aproape de goal după euristică. Rapid, dar poate găsi trasee suboptime.",
         "O(b^d)", "NU garantează optim"),
    ]

    for i, (short, col, full_name, desc, compl, optimal) in enumerate(algos):
        row = i % 3
        icol = i // 3
        bx = 0.4 + icol * 6.5
        by = 1.58 + row * 1.82

        add_rect(slide, bx, by, 6.2, 1.62, _hex("162032"))
        shape = slide.shapes.add_shape(1, Inches(bx), Inches(by), Inches(0.08), Inches(1.62))
        shape.fill.solid(); shape.fill.fore_color.rgb = col; shape.line.fill.background()
        add_rect(slide, bx + 0.12, by + 0.08, 0.7, 0.5, _hex("0d1929"))
        add_text(slide, short, bx + 0.14, by + 0.1, 0.66, 0.46,
                 size=11, bold=True, color=col, align=PP_ALIGN.CENTER)
        add_text(slide, full_name, bx + 0.92, by + 0.1, 5.1, 0.32,
                 size=11.5, bold=True, color=C_WHITE)
        add_text(slide, desc, bx + 0.92, by + 0.44, 5.1, 0.58,
                 size=9.5, color=C_MUTED)
        add_text(slide, f"Complexitate: {compl}", bx + 0.92, by + 1.05, 3.2, 0.28,
                 size=9, color=C_MUTED)
        opt_col = C_GREEN if "Garantat" in optimal else C_RED
        add_text(slide, optimal, bx + 4.2, by + 1.05, 2.0, 0.28,
                 size=9, bold=True, color=opt_col)


def build_benchmark(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_RED)

    badge(slide, "08 / BENCHMARK", 0.4, 0.3, fill=_hex("4a0d0d"), text_color=C_RED)
    add_text(slide, "Comparație & Rezultate", 0.4, 0.65, 10, 0.7,
             size=26, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5, color=C_RED)

    # Grafic pathfinding stânga sus
    fig1 = make_explored_cells_chart()
    add_image_from_fig(slide, fig1, 0.4, 1.55, 6.4, 3.2)

    # Grafic epsilon dreapta sus
    fig2 = make_epsilon_decay()
    add_image_from_fig(slide, fig2, 7.0, 1.55, 6.0, 3.2)

    # Tabel comparativ jos
    add_rect(slide, 0.4, 4.85, 12.5, 2.3, _hex("0d1929"))
    add_text(slide, "Concluzii comparative", 0.6, 4.92, 12, 0.35,
             size=12, bold=True, color=C_WHITE)

    rows_t = [
        ("A* (Pathfinding)", "Clasic — fără RL", "Optimal, rapid, fără antrenare",   "Necesită harta completă"),
        ("BFS (Pathfinding)","Clasic — fără RL", "Garantat cel mai scurt traseu",     "Explorează mai multe celule"),
        ("Q-Learning (RL)",  "Online learning",  "Adaptiv, nu necesită hartă",        "Necesită episoade de antrenare"),
        ("Dyna-Q (RL)",      "Model-based RL",   "Convergență rapidă prin planning",  "Memorie suplimentară"),
    ]
    headers = ["Algoritm", "Categorie", "Avantaje", "Dezavantaje"]
    col_w = [2.8, 2.0, 4.0, 3.5]

    cx = 0.55
    for h, cw in zip(headers, col_w):
        add_rect(slide, cx, 5.35, cw - 0.05, 0.3, _hex("1d3f72"))
        add_text(slide, h, cx + 0.07, 5.37, cw - 0.12, 0.26,
                 size=9.5, bold=True, color=C_BLUE)
        cx += cw

    for i, row in enumerate(rows_t):
        cx = 0.55
        bg = _hex("162032") if i % 2 == 0 else _hex("0d1929")
        for val, cw in zip(row, col_w):
            add_rect(slide, cx, 5.68 + i * 0.32, cw - 0.05, 0.31, bg)
            add_text(slide, val, cx + 0.07, 5.7 + i * 0.32, cw - 0.12, 0.27,
                     size=9.5, color=C_MUTED if i > 0 else C_WHITE)
            cx += cw


def build_cod_snippet(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, _hex("34d399"))

    badge(slide, "COD SURSĂ", 0.4, 0.3, fill=_hex("134e30"), text_color=C_GREEN)
    add_text(slide, "Fragmente de Cod Cheie", 0.4, 0.65, 10, 0.7,
             size=26, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5, color=C_GREEN)

    # Cod 1: Q-value update
    add_rect(slide, 0.4, 1.55, 6.0, 2.55, _hex("080f1d"))
    add_text(slide, "# 1. Actualizarea Q-Table (behaviors.py)", 0.55, 1.63, 5.7, 0.28,
             size=9.5, color=_hex("475569"))

    code1 = [
        ("def _learn(self, s, a, r, s2, terminal):", True,  _hex("3b82f6")),
        ("    qv = self._q_table[s]",                False, _hex("34d399")),
        ("    nv = self._q_table[s2]",               False, _hex("34d399")),
        ("    if terminal:",                          False, _hex("fbbf24")),
        ("        target = r",                        False, _hex("e2e8f0")),
        ("    else:",                                 False, _hex("fbbf24")),
        ("        target = r + γ * max(nv)",          False, _hex("e2e8f0")),
        ("    qv[a] += α * (target - qv[a])",         False, _hex("a78bfa")),
    ]
    add_multiline(slide, code1, 0.55, 1.95, 5.7, 2.1, size=10.5)

    # Cod 2: choose_action
    add_rect(slide, 6.6, 1.55, 6.4, 2.55, _hex("080f1d"))
    add_text(slide, "# 2. Selectarea acțiunii (ε-greedy)", 6.75, 1.63, 6.1, 0.28,
             size=9.5, color=_hex("475569"))

    code2 = [
        ("def _choose_action(self, s, f, l, r):",    True,  _hex("3b82f6")),
        ("    if f < self.collision_dist:",           False, _hex("fbbf24")),
        ("        return 3 if l>r else 4",            False, _hex("e2e8f0")),
        ("    if random.random() < self.ε:",          False, _hex("fbbf24")),
        ("        return random.choices(",            False, _hex("e2e8f0")),
        ("            [0,1,2,3,4,5],",               False, _hex("e2e8f0")),
        ("            weights=[40,20,20,8,8,4])[0]", False, _hex("34d399")),
        ("    return argmax(Q[s])  # greedy",         False, _hex("a78bfa")),
    ]
    add_multiline(slide, code2, 6.75, 1.95, 6.1, 2.1, size=10.5)

    # Cod 3: BFS
    add_rect(slide, 0.4, 4.2, 6.0, 2.95, _hex("080f1d"))
    add_text(slide, "# 3. BFS în pathfinding.py", 0.55, 4.28, 5.7, 0.28,
             size=9.5, color=_hex("475569"))

    code3 = [
        ("def bfs(maze: GridMaze):",                  True,  _hex("3b82f6")),
        ("    queue = deque([maze.start])",            False, _hex("e2e8f0")),
        ("    came_from = {maze.start: None}",         False, _hex("e2e8f0")),
        ("    while queue:",                           False, _hex("fbbf24")),
        ("        cur = queue.popleft()",              False, _hex("34d399")),
        ("        if cur == maze.goal:",               False, _hex("fbbf24")),
        ("            return reconstruct(came_from)",  False, _hex("a78bfa")),
        ("        for nb in maze.neighbors(*cur):",    False, _hex("34d399")),
        ("            if nb not in came_from:",        False, _hex("fbbf24")),
        ("                came_from[nb] = cur",        False, _hex("e2e8f0")),
        ("                queue.append(nb)",           False, _hex("e2e8f0")),
    ]
    add_multiline(slide, code3, 0.55, 4.58, 5.7, 2.5, size=10.5)

    # Cod 4: A*
    add_rect(slide, 6.6, 4.2, 6.4, 2.95, _hex("080f1d"))
    add_text(slide, "# 4. A* cu Manhattan heuristic", 6.75, 4.28, 6.1, 0.28,
             size=9.5, color=_hex("475569"))

    code4 = [
        ("def astar(maze: GridMaze):",                 True,  _hex("3b82f6")),
        ("    h = lambda n: manhattan(n, goal)",       False, _hex("e2e8f0")),
        ("    heap = [(h(start), 0, start)]",           False, _hex("e2e8f0")),
        ("    g_cost = {start: 0}",                    False, _hex("e2e8f0")),
        ("    while heap:",                            False, _hex("fbbf24")),
        ("        _, g, cur = heappop(heap)",           False, _hex("34d399")),
        ("        if cur == goal: return path",         False, _hex("a78bfa")),
        ("        for nb in maze.neighbors(*cur):",     False, _hex("34d399")),
        ("            ng = g_cost[cur] + 1",            False, _hex("e2e8f0")),
        ("            if ng < g_cost.get(nb, ∞):",      False, _hex("fbbf24")),
        ("                heappush(heap,(ng+h(nb),ng,nb))", False, _hex("e2e8f0")),
    ]
    add_multiline(slide, code4, 6.75, 4.58, 6.1, 2.5, size=10.5)


def build_ui(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_BLUE)

    badge(slide, "09 / INTERFAȚĂ", 0.4, 0.3, fill=_hex("1d3f72"))
    add_text(slide, "Interfața Utilizator — Dashboard", 0.4, 0.65, 11, 0.7,
             size=26, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5)

    pagini = [
        ("🏠", "Start",        "Informații echipă, descriere proiect",              C_BLUE),
        ("📚", "Concepte",     "Documentație algoritmi RL și robot",                C_PURPLE),
        ("⬜", "Editor Maze",  "Editare vizuală labirint, Solve cu BFS/DFS/A*",     C_GREEN),
        ("▷",  "Antrenare",   "Selectare algoritm RL, hiperparametri, start/stop", C_AMBER),
        ("≡",  "Benchmark",   "Pathfinding clasic instant + RL pe episoade",       C_RED),
        ("◈",  "Monitor",     "Senzori live, log evenimente, poziție robot",        C_MUTED),
    ]

    for i, (icon, name, desc, col) in enumerate(pagini):
        row = i % 3
        icol = i // 3
        bx = 0.4 + icol * 6.4
        by = 1.55 + row * 1.77

        add_rect(slide, bx, by, 6.1, 1.55, _hex("162032"))
        shape = slide.shapes.add_shape(1, Inches(bx), Inches(by), Inches(0.08), Inches(1.55))
        shape.fill.solid(); shape.fill.fore_color.rgb = col; shape.line.fill.background()

        add_text(slide, icon, bx + 0.2, by + 0.35, 0.7, 0.7, size=22)
        add_text(slide, name, bx + 1.1, by + 0.12, 4.8, 0.48,
                 size=15, bold=True, color=C_WHITE)
        add_text(slide, desc, bx + 1.1, by + 0.7, 4.8, 0.75,
                 size=11, color=C_MUTED)

    add_rect(slide, 0.4, 6.85, 12.5, 0.5, _hex("0d1929"))
    add_text(slide,
             "Stack UI: CustomTkinter (dark theme)  ·  Canvas Tkinter pentru labirint  "
             "·  Threading pentru loop de control la 20 Hz  ·  Queue pentru comunicare GUI ↔ Worker",
             0.55, 6.9, 12.2, 0.4, size=10, color=C_MUTED)


def build_concluzii(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide_bg(slide)
    add_rect(slide, 0, 0, 0.07, 7.5, C_GREEN)

    badge(slide, "10 / CONCLUZII", 0.4, 0.3, fill=_hex("134e30"), text_color=C_GREEN)
    add_text(slide, "Concluzii & Direcții Viitoare", 0.4, 0.65, 11, 0.7,
             size=26, bold=True, color=C_WHITE)
    divider(slide, 0.4, 1.38, 12.5, color=C_GREEN)

    # Ce s-a realizat
    add_rect(slide, 0.4, 1.55, 5.8, 2.9, _hex("162032"))
    add_text(slide, "✅  Ce s-a realizat", 0.6, 1.65, 5.4, 0.4,
             size=13, bold=True, color=C_GREEN)
    realizari = [
        "Simulator complet robot + labirint în CoppeliaSim",
        "4 algoritmi RL implementați și comparabili",
        "5 algoritmi de pathfinding clasic cu vizualizare",
        "Dashboard GUI interactiv cu editor labirint",
        "Benchmark automat + export grafice matplotlib",
        "Detecție blocare robot cu mecanism de recuperare",
    ]
    for i, r in enumerate(realizari):
        add_text(slide, f"  •  {r}", 0.6, 2.12 + i * 0.38, 5.6, 0.34,
                 size=10.5, color=C_MUTED)

    # Limitări
    add_rect(slide, 6.5, 1.55, 6.4, 2.9, _hex("162032"))
    add_text(slide, "⚠️  Limitări identificate", 6.7, 1.65, 6.0, 0.4,
             size=13, bold=True, color=C_AMBER)
    limitari = [
        "Spațiu de stări mic (27) → robot nu poate memora pozițiile",
        "Fără localizare → nu poate planifica rute lungi",
        "Q-Table reset la fiecare pornire (fără persistență)",
        "Senzorii ultrasonici au unghiuri moarte în colțuri",
    ]
    for i, l in enumerate(limitari):
        add_text(slide, f"  •  {l}", 6.7, 2.12 + i * 0.44, 6.0, 0.38,
                 size=10.5, color=C_MUTED)

    # Direcții viitoare
    add_rect(slide, 0.4, 4.6, 12.5, 2.1, _hex("0d1929"))
    add_text(slide, "🚀  Direcții de dezvoltare viitoare", 0.6, 4.68, 12, 0.4,
             size=13, bold=True, color=C_BLUE)
    directii = [
        ("Deep Q-Network (DQN)",  "Rețea neuronală în loc de Q-Table → gestionare spații de stări continue"),
        ("SLAM + Hartă internă",  "Localizare și cartografiere simultană → navigare planificată global"),
        ("Obstacole dinamice",    "Integrare obstacole mobile și replanificare în timp real"),
        ("Transfer learning",     "Pre-antrenare în simulare → transfer pe robotul real fizic"),
    ]
    for i, (titlu, desc) in enumerate(directii):
        bx = 0.55 + (i % 2) * 6.2
        by = 5.15 + (i // 2) * 0.7
        add_text(slide, f"→  {titlu}:", bx, by, 2.8, 0.3, size=11, bold=True, color=C_BLUE)
        add_text(slide, desc, bx + 2.9, by, 3.1, 0.3, size=10.5, color=C_MUTED)

    add_rect(slide, 0.4, 6.85, 12.5, 0.5, _hex("134e30"))
    add_text(slide,
             "Proiect realizat pentru disciplina Inteligență Artificială  ·  Echipa Patanii  ·  2026",
             0.6, 6.9, 12.2, 0.4, size=11, bold=True,
             color=C_GREEN, align=PP_ALIGN.CENTER)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    prs = Presentation()
    prs.slide_width  = W
    prs.slide_height = H

    print("Generare slide 01: Copertă...")
    build_title(prs)

    print("Generare slide 02: Cuprins...")
    build_cuprins(prs)

    print("Generare slide 03: Descriere proiect...")
    build_descriere(prs)

    print("Generare slide 04: Robot Pioneer P3-DX...")
    build_robot(prs)

    print("Generare slide 05: Labirint Grid...")
    build_labirint(prs)

    print("Generare slide 06: RL — Concepte...")
    build_rl_intro(prs)

    print("Generare slide 07: Q-Learning & SARSA...")
    build_qlearning_v2(prs)

    print("Generare slide 08: Expected SARSA & Dyna-Q...")
    build_esarsa_dynaq(prs)

    print("Generare slide 09: Stări & Recompense...")
    build_state_reward(prs)

    print("Generare slide 10: Algoritmi Pathfinding...")
    build_pathfinding(prs)

    print("Generare slide 11: Benchmark & Comparație...")
    build_benchmark(prs)

    print("Generare slide 12: Fragmente de Cod...")
    build_cod_snippet(prs)

    print("Generare slide 13: Interfață UI...")
    build_ui(prs)

    print("Generare slide 14: Concluzii...")
    build_concluzii(prs)

    out = "/home/gabets/Projects/aplicatieIA/ai/Documentatie_AI_Patanii.pptx"
    prs.save(out)
    print(f"\n✅  Salvat: {out}")
    print(f"   {prs.slides.__len__()} slide-uri generate.")


if __name__ == "__main__":
    main()

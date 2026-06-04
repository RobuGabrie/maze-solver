"""
gui/app.py - Steel-Blue Modern Dashboard
Reworked visual design: dark navy + sky-blue + emerald palette.
All functionality from v3 preserved.
"""
import datetime
import math
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageOps

import customtkinter as ctk
try:
    from PIL import ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

from core.behaviors import QLearningBehavior, SENSOR_LABELS, BehaviorBase, DT
from core.pathfinding import ALGORITHMS, PathResult
from core.grid_rl import RUNNERS, GridEnv
from core.maze import (
    GridMaze,
    WALL_HEX,
    BOUNDARY_HEX,
    clear_grid_maze,
    generate_maze,
    load_maze_presets_with_names,
    save_maze_presets,
    setup_grid_maze,
)
from core.robot import Robot, SensorReading

_ROOT = Path(__file__).parent.parent
_CONFIG = _ROOT / "config" / "mazes.json"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── Steel-Blue color palette ──────────────────────────────────────────
_SB_SIDEBAR   = "#0d1520"   # sidebar background
_SB_APP_BG    = "#0f1923"   # main content background
_SB_CARD      = "#162032"   # card / panel background
_SB_CARD_B    = "#1e3a5c"   # card border
_SB_ACCENT    = "#3b82f6"   # primary blue accent
_SB_ACCENT2   = "#34d399"   # secondary emerald accent
_SB_WARN      = "#fbbf24"   # amber / warning
_SB_DANGER    = "#f87171"   # soft red
_SB_PURPLE    = "#a78bfa"   # purple highlight
_SB_TEXT      = "#e2e8f0"   # primary text
_SB_MUTED     = "#64748b"   # muted / secondary text
_SB_ACTIVE    = "#1d3f72"   # active sidebar item bg

# ── Maze canvas colors (completely different from previous neon theme) ─
_C_BG        = "#080f1d"   # canvas background
_C_CELL      = "#0e1a2e"   # empty cell fill
_C_EXPLORED  = "#162d52"   # explored cell
_C_PATH      = "#34d399"   # optimal path (emerald)
_C_START     = "#3b82f6"   # start node (blue)
_C_GOAL      = "#fbbf24"   # goal node (amber)
_C_WALL      = "#7c3aed"   # internal walls (purple)
_C_BOUNDARY  = "#475569"   # outer boundary (steel)
_C_ROBOT     = "#f87171"   # robot position (soft red)

_MARGIN = 20


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AI Navigator — Maze RL Suite")
        self.geometry("1340x840")
        self.minsize(1155, 720)
        self.configure(fg_color=_SB_APP_BG)

        self.robot = Robot()
        self._maze: GridMaze = GridMaze(7, 7)
        self._presets: dict[str, tuple[str, GridMaze]] = {}
        self._cell_size_m: float = 0.5
        self._mobiles: list[dict] = []
        self._selected_mobile: int | None = None
        self._placing_mobile: bool = False
        self._adding_waypoint: bool = False
        self._hover_cell: tuple[int, int] | None = None

        self._path_result: PathResult | None = None
        self._solve_algo_var = ctk.StringVar(value="A* (Manhattan)")

        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._q: queue.Queue = queue.Queue(maxsize=10)

        self._rows_var = ctk.StringVar(value="7")
        self._cols_var = ctk.StringVar(value="7")
        self._exp_episodes = ctk.StringVar(value="50")

        self._build_main_layout()
        self._load_presets()
        self._poll()
        self._select_menu("home")

    # ══════════════════════════════════════════════════════════════
    # Layout
    # ══════════════════════════════════════════════════════════════

    def _build_main_layout(self) -> None:
        # ── Sidebar ───────────────────────────────────────────────
        self._sidebar = ctk.CTkFrame(self, width=230, corner_radius=0, fg_color=_SB_SIDEBAR)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        logo_frame = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=16, pady=(22, 4))
        ctk.CTkLabel(logo_frame, text="⬡", font=ctk.CTkFont(size=28), text_color=_SB_ACCENT).pack(side="left", padx=(0, 8))
        title_col = ctk.CTkFrame(logo_frame, fg_color="transparent")
        title_col.pack(side="left")
        ctk.CTkLabel(title_col, text="AI Navigator", font=ctk.CTkFont(size=17, weight="bold"), text_color=_SB_TEXT).pack(anchor="w")
        ctk.CTkLabel(title_col, text="RL Benchmark Suite", font=ctk.CTkFont(size=10), text_color=_SB_MUTED).pack(anchor="w")

        _divider(self._sidebar, color="#1a2d47")

        self._menu_btns = {}
        menu_specs = [
            ("home",    "◉  Start",              "Home & Team Info"),
            ("doc",     "◎  Concepts",            "Algorithms & Docs"),
            ("maze",    "⬜  Maze Editor",         "Visual Maze Builder"),
            ("train",   "▷  Train Agent",          "RL Training Control"),
            ("bench",   "≡  Benchmark",            "Multi-Model Compare"),
            ("monitor", "◈  Monitor",             "Sensors & Logs"),
        ]
        nav_section = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        nav_section.pack(fill="x", padx=10, pady=6)

        for key, label, _ in menu_specs:
            btn = ctk.CTkButton(
                nav_section, text=label, anchor="w", height=38,
                corner_radius=8,
                fg_color="transparent",
                text_color=_SB_MUTED,
                hover_color="#1a2d47",
                font=ctk.CTkFont(size=13),
                command=lambda k=key: self._select_menu(k)
            )
            btn.pack(fill="x", pady=2)
            self._menu_btns[key] = btn

        # ── Connection section (bottom of sidebar) ────────────────
        _divider(self._sidebar, color="#1a2d47")
        conn_frame = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        conn_frame.pack(side="bottom", fill="x", padx=12, pady=14)

        ctk.CTkLabel(
            conn_frame, text="SIMULATOR", font=ctk.CTkFont(size=9, weight="bold"),
            text_color=_SB_MUTED
        ).pack(anchor="w", padx=4, pady=(0, 4))

        self._host = ctk.CTkEntry(
            conn_frame, placeholder_text="localhost", height=30,
            fg_color="#0d1929", border_color="#1e3a5c", text_color=_SB_TEXT
        )
        self._host.insert(0, "localhost")
        self._host.pack(fill="x", pady=2)

        self._port = ctk.CTkEntry(
            conn_frame, placeholder_text="23000", height=30,
            fg_color="#0d1929", border_color="#1e3a5c", text_color=_SB_TEXT
        )
        self._port.insert(0, "23000")
        self._port.pack(fill="x", pady=2)

        self._conn_btn = ctk.CTkButton(
            conn_frame, text="Connect", height=34,
            fg_color=_SB_ACCENT, hover_color="#2563eb",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_connect
        )
        self._conn_btn.pack(fill="x", pady=(6, 3))

        status_row = ctk.CTkFrame(conn_frame, fg_color="transparent")
        status_row.pack(fill="x")
        ctk.CTkLabel(status_row, text="●", font=ctk.CTkFont(size=14), text_color=_SB_DANGER).pack(side="left")
        self._conn_lbl = ctk.CTkLabel(
            status_row, text=" Disconnected",
            font=ctk.CTkFont(size=11), text_color=_SB_MUTED
        )
        self._conn_lbl.pack(side="left")
        self._conn_dot = status_row.winfo_children()[0]

        # ── Content area ──────────────────────────────────────────
        self._content_container = ctk.CTkFrame(self, fg_color=_SB_APP_BG, corner_radius=0)
        self._content_container.pack(side="left", fill="both", expand=True)

        self._pages = {
            "home":    ctk.CTkScrollableFrame(self._content_container, fg_color="transparent"),
            "doc":     ctk.CTkScrollableFrame(self._content_container, fg_color="transparent"),
            "maze":    ctk.CTkFrame(self._content_container, fg_color="transparent"),
            "train":   ctk.CTkFrame(self._content_container, fg_color="transparent"),
            "bench":   ctk.CTkFrame(self._content_container, fg_color="transparent"),
            "monitor": ctk.CTkFrame(self._content_container, fg_color="transparent"),
        }

        self._build_home_page(self._pages["home"])
        self._build_doc_page(self._pages["doc"])
        self._build_maze_page(self._pages["maze"])
        self._build_train_page(self._pages["train"])
        self._build_bench_page(self._pages["bench"])
        self._build_monitor_page(self._pages["monitor"])

    def _select_menu(self, target_key: str) -> None:
        for key, page in self._pages.items():
            page.pack_forget()
            self._menu_btns[key].configure(
                fg_color="transparent", text_color=_SB_MUTED, border_width=0
            )
        self._pages[target_key].pack(fill="both", expand=True, padx=18, pady=18)
        self._menu_btns[target_key].configure(
            fg_color=_SB_ACTIVE, text_color=_SB_ACCENT,
            border_width=1, border_color=_SB_CARD_B
        )
        if target_key in ("maze", "train"):
            self._redraw()

    # ══════════════════════════════════════════════════════════════
    # 1. Home Page
    # ══════════════════════════════════════════════════════════════

    def _build_home_page(self, parent: ctk.CTkScrollableFrame) -> None:
        # Hero banner
        hero = _card(parent, border_color=_SB_CARD_B)
        hero.pack(fill="x", pady=(0, 16))

        badge = ctk.CTkFrame(hero, fg_color="#1d3f72", corner_radius=6)
        badge.pack(anchor="w", padx=20, pady=(18, 6))
        ctk.CTkLabel(
            badge, text="  PROIECT DILEMA · INTELIGENȚĂ ARTIFICIALĂ 2026  ",
            font=ctk.CTkFont(size=10, weight="bold"), text_color=_SB_ACCENT
        ).pack(padx=4, pady=3)

        ctk.CTkLabel(
            hero, text="Autonomous Navigation &\nRL Benchmark Platform",
            font=ctk.CTkFont(size=26, weight="bold"), text_color=_SB_TEXT, justify="left"
        ).pack(anchor="w", padx=20, pady=(4, 4))
        ctk.CTkLabel(
            hero, text="Pioneer P3-DX · CoppeliaSim · Q-Learning / SARSA / Dyna-Q",
            font=ctk.CTkFont(size=13), text_color=_SB_MUTED
        ).pack(anchor="w", padx=20, pady=(0, 18))

        # Team section
        ctk.CTkLabel(
            parent, text="TEAM MEMBERS",
            font=ctk.CTkFont(size=10, weight="bold"), text_color=_SB_MUTED
        ).pack(anchor="w", pady=(4, 8))

        cards_row = ctk.CTkFrame(parent, fg_color="transparent")
        cards_row.pack(fill="x")

        membri_detalii = [
            {"nume": "Rusu Sebastian",    "foto": "RusuS.jpeg"},
            {"nume": "Casciuc Stanislav", "foto": "CasciucS.jpeg"},
            {"nume": "Robu Gabriel",      "foto": "RobuG.jpeg"},
        ]

        for m in membri_detalii:
            card = ctk.CTkFrame(
                cards_row, width=210, height=240,
                fg_color=_SB_CARD, corner_radius=12,
                border_width=1, border_color=_SB_CARD_B
            )
            card.pack(side="left", padx=(0, 14), pady=4)
            card.pack_propagate(False)

            img_path = _ROOT / m["foto"]
            loaded = False
            if _PIL_OK and img_path.exists():
                try:
                    img = Image.open(img_path)
                    img = ImageOps.fit(img, (min(img.size), min(img.size)), Image.Resampling.LANCZOS)
                    img = img.resize((120, 120), Image.Resampling.LANCZOS)
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(120, 120))
                    avatar = ctk.CTkLabel(card, image=ctk_img, text="", corner_radius=60)
                    avatar.pack(pady=(20, 8))
                    loaded = True
                except Exception:
                    pass

            if not loaded:
                av_box = ctk.CTkFrame(card, width=120, height=120, fg_color="#1a2d47", corner_radius=60)
                av_box.pack(pady=(20, 8))
                av_box.pack_propagate(False)
                ctk.CTkLabel(av_box, text="👤", font=ctk.CTkFont(size=42)).pack(expand=True)

            ctk.CTkLabel(
                card, text=m["nume"],
                font=ctk.CTkFont(size=13, weight="bold"), text_color=_SB_TEXT, wraplength=180
            ).pack(pady=(0, 3))
            ctk.CTkLabel(
                card, text="AI Research / Developer",
                font=ctk.CTkFont(size=10), text_color=_SB_MUTED
            ).pack()

    # ══════════════════════════════════════════════════════════════
    # 2. Documentation Page
    # ══════════════════════════════════════════════════════════════

    def _build_doc_page(self, parent: ctk.CTkScrollableFrame) -> None:
        _page_header(parent, "Concepts & Algorithms", "Technical reference for robot and RL models")

        sections = [
            (
                "🤖  Robot Capabilities",
                _SB_ACCENT,
                "The Pioneer P3-DX robot uses a circular array of 16 independent ultrasonic proximity sensors.\n"
                "Autonomous movement is determined kinematically by adjusting wheel velocities vL and vR.\n"
                "Objective: identify the shortest path and avoid dynamic obstacles until reaching the goal."
            ),
            (
                "🧠  Reinforcement Learning Architecture",
                _SB_ACCENT2,
                "Four major RL approaches are integrated:\n"
                "  1.  Q-Learning  —  Off-policy temporal difference (greedy target)\n"
                "  2.  SARSA  —  On-policy TD (follows current policy)\n"
                "  3.  Expected SARSA  —  Stable update via expected value over actions\n"
                "  4.  Dyna-Q  —  Combines direct env learning with simulated planning steps"
            ),
            (
                "⚙️  State & Action Space",
                _SB_PURPLE,
                "State: 3 sensor zones (front, left, right) each bucketed into 3 distance ranges → 27 discrete states.\n"
                "Actions: FORWARD, CURVE_LEFT, CURVE_RIGHT, TURN_LEFT, TURN_RIGHT, BACK_UP.\n"
                "Exploration: ε-greedy with exponential decay. Stuck detection triggers forced recovery maneuvers."
            ),
        ]

        for title, color, body in sections:
            card = _card(parent, border_color=_SB_CARD_B)
            card.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(
                card, text=title, font=ctk.CTkFont(size=15, weight="bold"), text_color=color
            ).pack(anchor="w", padx=20, pady=(16, 6))
            ctk.CTkLabel(
                card, text=body, font=ctk.CTkFont(size=13),
                justify="left", wraplength=780, text_color=_SB_TEXT
            ).pack(anchor="w", padx=20, pady=(0, 16))

    # ══════════════════════════════════════════════════════════════
    # 3. Maze Editor Page
    # ══════════════════════════════════════════════════════════════

    def _build_maze_page(self, parent: ctk.CTkFrame) -> None:
        # Left control panel
        ctrl = ctk.CTkFrame(parent, width=270, fg_color=_SB_CARD, corner_radius=10, border_width=1, border_color=_SB_CARD_B)
        ctrl.pack(side="left", fill="y", padx=(0, 12), pady=0)
        ctrl.pack_propagate(False)

        _section_label(ctrl, "GRID SIZE")

        r_box = ctk.CTkFrame(ctrl, fg_color="transparent")
        r_box.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(r_box, text="Rows", width=64, anchor="w", text_color=_SB_MUTED, font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkEntry(r_box, textvariable=self._rows_var, width=72, fg_color="#0d1929", border_color=_SB_CARD_B).pack(side="left")

        c_box = ctk.CTkFrame(ctrl, fg_color="transparent")
        c_box.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(c_box, text="Cols", width=64, anchor="w", text_color=_SB_MUTED, font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkEntry(c_box, textvariable=self._cols_var, width=72, fg_color="#0d1929", border_color=_SB_CARD_B).pack(side="left")

        _primary_btn(ctrl, "Apply Size", self._on_resize).pack(fill="x", padx=14, pady=(6, 2))

        _divider(ctrl)
        _section_label(ctrl, "START / GOAL NODES")

        sg1 = ctk.CTkFrame(ctrl, fg_color="transparent")
        sg1.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(sg1, text="Start R:", width=58, anchor="w", text_color=_SB_MUTED, font=ctk.CTkFont(size=12)).pack(side="left")
        self._start_r = ctk.CTkEntry(sg1, width=46, fg_color="#0d1929", border_color=_SB_CARD_B)
        self._start_r.insert(0, "0")
        self._start_r.pack(side="left", padx=2)
        ctk.CTkLabel(sg1, text="C:", text_color=_SB_MUTED).pack(side="left", padx=2)
        self._start_c = ctk.CTkEntry(sg1, width=46, fg_color="#0d1929", border_color=_SB_CARD_B)
        self._start_c.insert(0, "0")
        self._start_c.pack(side="left")

        sg2 = ctk.CTkFrame(ctrl, fg_color="transparent")
        sg2.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(sg2, text="Goal R:", width=58, anchor="w", text_color=_SB_MUTED, font=ctk.CTkFont(size=12)).pack(side="left")
        self._goal_r = ctk.CTkEntry(sg2, width=46, fg_color="#0d1929", border_color=_SB_CARD_B)
        self._goal_r.insert(0, "6")
        self._goal_r.pack(side="left", padx=2)
        ctk.CTkLabel(sg2, text="C:", text_color=_SB_MUTED).pack(side="left", padx=2)
        self._goal_c = ctk.CTkEntry(sg2, width=46, fg_color="#0d1929", border_color=_SB_CARD_B)
        self._goal_c.insert(0, "6")
        self._goal_c.pack(side="left")

        _primary_btn(ctrl, "Set Start / Goal", self._on_set_start_goal, color=_SB_ACCENT2).pack(fill="x", padx=14, pady=(6, 2))

        _divider(ctrl)
        _section_label(ctrl, "GENERATION")

        self._gen_type_var = ctk.StringVar(value="Perfect (DFS)")
        ctk.CTkComboBox(
            ctrl, values=["Perfect (DFS)", "Random (Density)"],
            variable=self._gen_type_var,
            fg_color="#0d1929", border_color=_SB_CARD_B,
            button_color=_SB_ACCENT, dropdown_fg_color=_SB_CARD
        ).pack(fill="x", padx=14, pady=3)

        d_row = ctk.CTkFrame(ctrl, fg_color="transparent")
        d_row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(d_row, text="Density", width=60, anchor="w", text_color=_SB_MUTED, font=ctk.CTkFont(size=12)).pack(side="left")
        self._density_slider = ctk.CTkSlider(d_row, from_=0.1, to=0.6, number_of_steps=10, button_color=_SB_ACCENT, progress_color=_SB_ACCENT)
        self._density_slider.set(0.25)
        self._density_slider.pack(side="left", fill="x", expand=True)

        _primary_btn(ctrl, "Generate Maze", self._on_generate).pack(fill="x", padx=14, pady=(6, 2))
        _ghost_btn(ctrl, "Clear All Walls", self._on_clear_walls).pack(fill="x", padx=14, pady=2)

        _divider(ctrl)
        _section_label(ctrl, "PRESETS")

        self._preset_cb = ctk.CTkComboBox(
            ctrl, command=self._on_load_preset,
            fg_color="#0d1929", border_color=_SB_CARD_B,
            button_color=_SB_ACCENT, dropdown_fg_color=_SB_CARD
        )
        self._preset_cb.pack(fill="x", padx=14, pady=3)
        _primary_btn(ctrl, "Save Preset", self._on_save_preset, color="#1a6b3c").pack(fill="x", padx=14, pady=2)

        _divider(ctrl)
        _section_label(ctrl, "PATHFINDING")

        self._solve_algo_cb = ctk.CTkComboBox(
            ctrl, values=list(ALGORITHMS.keys()),
            variable=self._solve_algo_var,
            fg_color="#0d1929", border_color=_SB_CARD_B,
            button_color=_SB_ACCENT, dropdown_fg_color=_SB_CARD
        )
        self._solve_algo_cb.pack(fill="x", padx=14, pady=3)

        _primary_btn(ctrl, "▶  Solve Maze", self._on_solve, color=_SB_ACCENT2).pack(fill="x", padx=14, pady=(4, 2))
        _ghost_btn(ctrl, "Clear Path", self._on_clear_path).pack(fill="x", padx=14, pady=2)

        self._solve_info = ctk.CTkLabel(
            ctrl, text="", font=ctk.CTkFont(family="Courier", size=10),
            text_color=_SB_MUTED, wraplength=220, justify="left"
        )
        self._solve_info.pack(fill="x", padx=14, pady=4)

        # Canvas area
        canvas_frame = ctk.CTkFrame(parent, fg_color=_SB_CARD, corner_radius=10, border_width=1, border_color=_SB_CARD_B)
        canvas_frame.pack(side="left", fill="both", expand=True)

        hint_bar = ctk.CTkFrame(canvas_frame, fg_color="transparent")
        hint_bar.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(
            hint_bar,
            text="Left-click: Toggle Wall  ·  Right-click on cell: Move Start/Goal",
            font=ctk.CTkFont(size=11), text_color=_SB_MUTED
        ).pack(side="left")

        self._canvas = tk.Canvas(canvas_frame, bg=_C_BG, highlightthickness=1, highlightbackground=_SB_CARD_B)
        self._canvas.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self._canvas.bind("<Configure>", lambda _: self._redraw())
        self._canvas.bind("<Button-1>", self._on_canvas_left)
        self._canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self._canvas.bind("<Button-3>", self._on_canvas_right)

    # ══════════════════════════════════════════════════════════════
    # 4. Training Page
    # ══════════════════════════════════════════════════════════════

    def _build_train_page(self, parent: ctk.CTkFrame) -> None:
        left = ctk.CTkFrame(parent, width=320, fg_color=_SB_CARD, corner_radius=10, border_width=1, border_color=_SB_CARD_B)
        left.pack(side="left", fill="y", padx=(0, 12), pady=0)
        left.pack_propagate(False)

        _section_label(left, "ALGORITHM")
        self._algo_var = ctk.StringVar(value="Q-learning")
        self._algo_selector = ctk.CTkOptionMenu(
            left, values=["Q-learning", "SARSA", "Expected SARSA", "Dyna-Q"],
            variable=self._algo_var,
            fg_color=_SB_ACCENT, button_color="#2563eb",
            dropdown_fg_color=_SB_CARD, font=ctk.CTkFont(size=13, weight="bold")
        )
        self._algo_selector.pack(fill="x", padx=14, pady=(4, 8))

        _divider(left)
        self._params_frame = ctk.CTkScrollableFrame(
            left, label_text="Hyperparameters",
            fg_color="transparent",
            label_text_color=_SB_MUTED, label_font=ctk.CTkFont(size=10, weight="bold")
        )
        self._params_frame.pack(fill="both", expand=True, padx=8, pady=6)
        self._param_sliders: dict[str, ctk.CTkSlider] = {}
        self._param_val_lbls: dict[str, ctk.CTkLabel] = {}
        self._rebuild_learning_params()

        # Right side
        right = ctk.CTkFrame(parent, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        # Simulator sync card
        sim_card = _card(right, border_color=_SB_CARD_B)
        sim_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            sim_card, text="CoppeliaSim Scene",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=_SB_ACCENT
        ).pack(anchor="w", padx=18, pady=(14, 8))

        sz_row = ctk.CTkFrame(sim_card, fg_color="transparent")
        sz_row.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(sz_row, text="Cell size (m):", text_color=_SB_MUTED, font=ctk.CTkFont(size=12)).pack(side="left")
        self._cell_m = ctk.CTkEntry(sz_row, width=72, fg_color="#0d1929", border_color=_SB_CARD_B)
        self._cell_m.insert(0, "0.5")
        self._cell_m.pack(side="left", padx=10)

        btn_row = ctk.CTkFrame(sim_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(0, 14))
        _primary_btn(btn_row, "Sync Maze → CoppeliaSim", self._on_apply_maze).pack(side="left", fill="x", expand=True, padx=(0, 6))
        _ghost_btn(btn_row, "Clear Scene", self._on_clear_scene).pack(side="left")

        # Execution card
        exec_card = _card(right, border_color=_SB_CARD_B)
        exec_card.pack(fill="both", expand=True)

        ctk.CTkLabel(
            exec_card, text="Agent Execution",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=_SB_ACCENT
        ).pack(anchor="w", padx=18, pady=(14, 8))

        ctrl_row = ctk.CTkFrame(exec_card, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=18, pady=(0, 10))
        self._start_btn = ctk.CTkButton(
            ctrl_row, text="▶  Start Training",
            fg_color="#166534", hover_color="#15803d",
            font=ctk.CTkFont(size=14, weight="bold"), height=44, corner_radius=8,
            command=self._on_start_beh
        )
        self._start_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._stop_btn = ctk.CTkButton(
            ctrl_row, text="■  Stop",
            fg_color="#7f1d1d", hover_color="#991b1b",
            font=ctk.CTkFont(size=14, weight="bold"), height=44, corner_radius=8,
            state="disabled", command=self._on_stop_beh
        )
        self._stop_btn.pack(side="left")

        status_card = ctk.CTkFrame(exec_card, fg_color="#0d1929", corner_radius=8)
        status_card.pack(fill="x", padx=18, pady=(0, 14))
        self._beh_status = ctk.CTkLabel(
            status_card, text="Agent Status: Idle",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w", text_color=_SB_ACCENT2
        )
        self._beh_status.pack(fill="x", padx=12, pady=(8, 4))
        self._vel_lbl = ctk.CTkLabel(
            status_card, text="Motors: vL = 0.00  ·  vR = 0.00",
            font=ctk.CTkFont(family="Courier", size=12), anchor="w", text_color=_SB_MUTED
        )
        self._vel_lbl.pack(fill="x", padx=12, pady=(0, 8))

    # ══════════════════════════════════════════════════════════════
    # 5. Benchmark Page
    # ══════════════════════════════════════════════════════════════

    def _build_bench_page(self, parent: ctk.CTkFrame) -> None:
        # ── Left column: Classical pathfinding benchmark (no simulator needed) ──
        left_col = ctk.CTkFrame(parent, width=420, fg_color="transparent")
        left_col.pack(side="left", fill="y", padx=(0, 12))
        left_col.pack_propagate(False)

        classical_card = _card(left_col, border_color=_SB_CARD_B)
        classical_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            classical_card, text="Classical Pathfinding",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=_SB_ACCENT2
        ).pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(
            classical_card, text="Runs instantly on the current maze — no simulator required.",
            font=ctk.CTkFont(size=11), text_color=_SB_MUTED
        ).pack(anchor="w", padx=16, pady=(0, 10))

        _primary_btn(
            classical_card, "▶  Run All 5 Algorithms", self._on_run_classical, color=_SB_ACCENT2
        ).pack(fill="x", padx=16, pady=(0, 14))

        results_card = _card(left_col, border_color=_SB_CARD_B)
        results_card.pack(fill="both", expand=True)

        ctk.CTkLabel(
            results_card, text="RESULTS",
            font=ctk.CTkFont(size=9, weight="bold"), text_color=_SB_MUTED
        ).pack(anchor="w", padx=16, pady=(12, 4))

        self._classical_output = ctk.CTkTextbox(
            results_card,
            fg_color="#080f1d",
            font=ctk.CTkFont(family="Courier", size=12),
            text_color=_SB_ACCENT2,
            state="disabled",
            border_width=1, border_color=_SB_CARD_B,
            corner_radius=8
        )
        self._classical_output.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # ── Right column: RL benchmark (grid simulation, no simulator needed) ─
        right_col = ctk.CTkFrame(parent, fg_color="transparent")
        right_col.pack(side="left", fill="both", expand=True)

        top = _card(right_col, border_color=_SB_CARD_B)
        top.pack(fill="x", pady=(0, 10))

        left_top = ctk.CTkFrame(top, fg_color="transparent")
        left_top.pack(side="left", fill="y", padx=16, pady=12)
        ctk.CTkLabel(
            left_top, text="RL Model Benchmark",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=_SB_TEXT
        ).pack(anchor="w")
        ctk.CTkLabel(
            left_top, text="Grid simulation — no simulator required",
            font=ctk.CTkFont(size=11), text_color=_SB_MUTED
        ).pack(anchor="w")

        right_top = ctk.CTkFrame(top, fg_color="transparent")
        right_top.pack(side="right", padx=16, pady=12)
        ctk.CTkLabel(right_top, text="Episodes:", text_color=_SB_MUTED,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        ctk.CTkEntry(right_top, textvariable=self._exp_episodes, width=60,
                     fg_color="#0d1929", border_color=_SB_CARD_B).pack(side="left", padx=(0, 10))
        self._btn_bench = ctk.CTkButton(
            right_top, text="⚡  Run RL Benchmark",
            fg_color=_SB_WARN, hover_color="#d97706", text_color="#0f1923",
            font=ctk.CTkFont(size=13, weight="bold"), height=36,
            command=self._on_run_compare
        )
        self._btn_bench.pack(side="left")

        # Chart image area
        chart_card = _card(right_col, border_color=_SB_CARD_B)
        chart_card.pack(fill="both", expand=True, pady=(0, 10))

        self._bench_chart_lbl = ctk.CTkLabel(
            chart_card,
            text="Apasă  ⚡ Run RL Benchmark  pentru a vedea graficul de convergență.",
            font=ctk.CTkFont(size=12), text_color=_SB_MUTED,
            fg_color="transparent"
        )
        self._bench_chart_lbl.pack(expand=True)

        # Summary textbox
        output_card = _card(right_col, border_color=_SB_CARD_B)
        output_card.pack(fill="x")

        ctk.CTkLabel(
            output_card, text="SUMMARY",
            font=ctk.CTkFont(size=9, weight="bold"), text_color=_SB_MUTED
        ).pack(anchor="w", padx=16, pady=(10, 4))

        self._exp_output = ctk.CTkTextbox(
            output_card,
            height=160,
            fg_color="#080f1d",
            font=ctk.CTkFont(family="Courier", size=12),
            text_color=_SB_ACCENT2,
            state="disabled",
            border_width=1, border_color=_SB_CARD_B,
            corner_radius=8
        )
        self._exp_output.pack(fill="x", padx=16, pady=(0, 14))

    # ══════════════════════════════════════════════════════════════
    # 6. Monitor Page
    # ══════════════════════════════════════════════════════════════

    def _build_monitor_page(self, parent: ctk.CTkFrame) -> None:
        # Sensor panel
        sens_card = _card(parent, border_color=_SB_CARD_B)
        sens_card.pack(side="left", fill="both", expand=True, padx=(0, 10))

        top_s = ctk.CTkFrame(sens_card, fg_color="transparent")
        top_s.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(
            top_s, text="Ultrasonic Array (16 channels)",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=_SB_TEXT
        ).pack(side="left")
        self._auto_refresh = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            top_s, text="Live", variable=self._auto_refresh, width=60,
            checkmark_color=_SB_ACCENT2, fg_color=_SB_ACCENT
        ).pack(side="right", padx=5)
        self._pos_lbl = ctk.CTkLabel(top_s, text="Pos: X=—  Y=—", text_color=_SB_MUTED, font=ctk.CTkFont(size=11))
        self._pos_lbl.pack(side="right", padx=12)

        scroll_s = ctk.CTkScrollableFrame(sens_card, fg_color="transparent")
        scroll_s.pack(fill="both", expand=True, padx=8, pady=4)

        self._sbars: list[ctk.CTkProgressBar] = []
        self._sdist: list[ctk.CTkLabel] = []
        for i, lbl in enumerate(SENSOR_LABELS):
            row = ctk.CTkFrame(scroll_s, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(
                row, text=f"[{i:02d}] {lbl}", width=144, anchor="w",
                font=ctk.CTkFont(family="Courier", size=11), text_color=_SB_MUTED
            ).pack(side="left", padx=2)
            bar = ctk.CTkProgressBar(row, width=150, progress_color=_SB_ACCENT, fg_color="#1a2d47")
            bar.set(0)
            bar.pack(side="left", padx=4)
            dl = ctk.CTkLabel(row, text="---", width=62, anchor="w", font=ctk.CTkFont(family="Courier", size=11), text_color=_SB_TEXT)
            dl.pack(side="left", padx=2)
            self._sbars.append(bar)
            self._sdist.append(dl)

        # Log panel
        log_card = ctk.CTkFrame(parent, width=400, fg_color=_SB_CARD, corner_radius=10, border_width=1, border_color=_SB_CARD_B)
        log_card.pack(side="right", fill="y")
        log_card.pack_propagate(False)

        ctk.CTkLabel(
            log_card, text="SYSTEM LOG",
            font=ctk.CTkFont(size=9, weight="bold"), text_color=_SB_MUTED
        ).pack(anchor="w", padx=14, pady=(12, 4))

        self._log_box = ctk.CTkTextbox(
            log_card,
            font=ctk.CTkFont(family="Courier", size=11),
            state="disabled",
            fg_color="#080f1d",
            text_color=_SB_ACCENT2,
            border_width=1, border_color=_SB_CARD_B
        )
        self._log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # ══════════════════════════════════════════════════════════════
    # Maze drawing & interaction
    # ══════════════════════════════════════════════════════════════

    def _cell_px(self, canvas: tk.Canvas) -> float:
        w = canvas.winfo_width() - 2 * _MARGIN
        h = canvas.winfo_height() - 2 * _MARGIN
        return max(5.0, min(w / self._maze.cols, h / self._maze.rows))

    def _maze_origin(self, canvas: tk.Canvas) -> tuple[float, float]:
        cp = self._cell_px(canvas)
        ox = (canvas.winfo_width()  - self._maze.cols * cp) / 2
        oy = (canvas.winfo_height() - self._maze.rows * cp) / 2
        return ox, oy

    def _redraw(self, robot_pos: tuple | None = None) -> None:
        canvas = self._canvas
        canvas.delete("all")
        if canvas.winfo_width() < 20:
            return

        cp = self._cell_px(canvas)
        ox, oy = self._maze_origin(canvas)
        rows, cols = self._maze.rows, self._maze.cols
        m = self._maze

        for r in range(rows):
            for c in range(cols):
                x0 = ox + c * cp
                y0 = oy + r * cp
                canvas.create_rectangle(x0, y0, x0 + cp, y0 + cp, fill=_C_CELL, outline="#0f1f35")

        # Draw explored cells (pathfinding visited nodes)
        if self._path_result:
            explored_set = set(self._path_result.explored)
            path_set = set(self._path_result.path) if self._path_result.path else set()
            for (er, ec) in explored_set - path_set:
                if 0 <= er < rows and 0 <= ec < cols:
                    x0 = ox + ec * cp + 1
                    y0 = oy + er * cp + 1
                    canvas.create_rectangle(x0, y0, x0 + cp - 2, y0 + cp - 2, fill=_C_EXPLORED, outline="")

            # Draw path cells
            if self._path_result.path:
                for (pr, pc) in self._path_result.path:
                    if 0 <= pr < rows and 0 <= pc < cols:
                        x0 = ox + pc * cp + 2
                        y0 = oy + pr * cp + 2
                        canvas.create_rectangle(x0, y0, x0 + cp - 4, y0 + cp - 4, fill=_C_PATH, outline="")

                # Draw path as a connected line on top
                pts = []
                for (pr, pc) in self._path_result.path:
                    pts.extend([ox + pc * cp + cp / 2, oy + pr * cp + cp / 2])
                if len(pts) >= 4:
                    canvas.create_line(pts, fill=_C_PATH, width=max(2, int(cp * 0.18)), smooth=True, capstyle="round")

        sr, sc = m.start
        gr, gc = m.goal
        _draw_marker(canvas, ox + sc * cp + cp / 2, oy + sr * cp + cp / 2, cp * 0.35, _C_START, "S")
        _draw_marker(canvas, ox + gc * cp + cp / 2, oy + gr * cp + cp / 2, cp * 0.35, _C_GOAL, "G")

        for r in range(rows + 1):
            for c in range(cols):
                if m.h_walls[r][c]:
                    is_b = m.is_boundary_h(r)
                    color = _C_BOUNDARY if is_b else _C_WALL
                    w = 4 if is_b else 2
                    x0 = ox + c * cp
                    y0 = oy + r * cp
                    canvas.create_line(x0, y0, x0 + cp, y0, fill=color, width=w)

        for r in range(rows):
            for c in range(cols + 1):
                if m.v_walls[r][c]:
                    is_b = m.is_boundary_v(c)
                    color = _C_BOUNDARY if is_b else _C_WALL
                    w = 4 if is_b else 2
                    x0 = ox + c * cp
                    y0 = oy + r * cp
                    canvas.create_line(x0, y0, x0, y0 + cp, fill=color, width=w)

        if robot_pos:
            rr, rc = robot_pos
            if 0 <= rr < rows and 0 <= rc < cols:
                rad = max(5, cp * 0.28)
                cx = ox + rc * cp + cp / 2
                cy = oy + rr * cp + cp / 2
                canvas.create_oval(cx - rad, cy - rad, cx + rad, cy + rad, fill=_C_ROBOT, outline="white", width=1)

    def _hit_wall(self, x: float, y: float) -> tuple[str, int, int] | None:
        cp = self._cell_px(self._canvas)
        ox, oy = self._maze_origin(self._canvas)
        rx, ry = x - ox, y - oy
        rows, cols = self._maze.rows, self._maze.cols
        THRESH = cp * 0.25
        best: tuple | None = None
        best_d = THRESH

        for r in range(rows + 1):
            wy = r * cp
            if abs(ry - wy) < best_d:
                c = int(rx / cp)
                if 0 <= c < cols:
                    best_d = abs(ry - wy)
                    best = ("h", r, c)

        for c in range(cols + 1):
            wx = c * cp
            if abs(rx - wx) < best_d:
                r = int(ry / cp)
                if 0 <= r < rows:
                    best_d = abs(rx - wx)
                    best = ("v", r, c)
        return best

    def _on_canvas_left(self, event: tk.Event) -> None:
        hit = self._hit_wall(event.x, event.y)
        if not hit:
            return
        wtype, wr, wc = hit
        if wtype == "h":
            self._maze.toggle_h_wall(wr, wc)
        else:
            self._maze.toggle_v_wall(wr, wc)
        self._last_toggled = hit
        self._redraw()

    def _on_canvas_drag(self, event: tk.Event) -> None:
        hit = self._hit_wall(event.x, event.y)
        if not hit or hit == getattr(self, "_last_toggled", None):
            return
        wtype, wr, wc = hit
        if wtype == "h":
            self._maze.toggle_h_wall(wr, wc)
        else:
            self._maze.toggle_v_wall(wr, wc)
        self._last_toggled = hit
        self._redraw()

    def _on_canvas_right(self, event: tk.Event) -> None:
        cp = self._cell_px(self._canvas)
        ox, oy = self._maze_origin(self._canvas)
        c = int((event.x - ox) / cp)
        r = int((event.y - oy) / cp)
        if not (0 <= r < self._maze.rows and 0 <= c < self._maze.cols):
            return
        if (r, c) == self._maze.start:
            self._maze.start = self._maze.goal
            self._maze.goal = (r, c)
        else:
            self._maze.start = (r, c)
        self._update_start_goal_entries()
        self._redraw()

    def _update_start_goal_entries(self) -> None:
        _set_entry(self._start_r, str(self._maze.start[0]))
        _set_entry(self._start_c, str(self._maze.start[1]))
        _set_entry(self._goal_r,  str(self._maze.goal[0]))
        _set_entry(self._goal_c,  str(self._maze.goal[1]))

    def _on_resize(self) -> None:
        try:
            rows = int(self._rows_var.get())
            cols = int(self._cols_var.get())
        except ValueError:
            return
        rows = _clamp(rows, 2, 25)
        cols = _clamp(cols, 2, 25)
        self._maze = GridMaze(rows, cols)
        self._path_result = None
        self._rows_var.set(str(rows))
        self._cols_var.set(str(cols))
        _set_entry(self._goal_r, str(rows - 1))
        _set_entry(self._goal_c, str(cols - 1))
        self._maze.goal = (rows - 1, cols - 1)
        self._redraw()

    def _on_set_start_goal(self) -> None:
        try:
            sr = _clamp(int(self._start_r.get()), 0, self._maze.rows - 1)
            sc = _clamp(int(self._start_c.get()), 0, self._maze.cols - 1)
            gr = _clamp(int(self._goal_r.get()),  0, self._maze.rows - 1)
            gc = _clamp(int(self._goal_c.get()),  0, self._maze.cols - 1)
        except ValueError:
            return
        self._maze.start = (sr, sc)
        self._maze.goal  = (gr, gc)
        self._redraw()

    def _on_generate(self) -> None:
        try:
            rows = int(self._rows_var.get())
            cols = int(self._cols_var.get())
        except ValueError:
            rows, cols = self._maze.rows, self._maze.cols
        rows = _clamp(rows, 2, 25)
        cols = _clamp(cols, 2, 25)

        gen_type = self._gen_type_var.get()
        if gen_type == "Perfect (DFS)":
            self._maze = generate_maze(rows, cols)
            self.log(f"Generated perfect maze {rows}x{cols} (DFS).")
        else:
            import random
            new_maze = GridMaze(rows, cols)
            density = self._density_slider.get()
            for r in range(1, rows):
                for c in range(cols):
                    if random.random() < density:
                        new_maze.h_walls[r][c] = True
            for r in range(rows):
                for c in range(1, cols):
                    if random.random() < density:
                        new_maze.v_walls[r][c] = True
            sr, sc = new_maze.start
            new_maze.h_walls[sr][sc] = False
            new_maze.h_walls[sr + 1][sc] = False
            new_maze.v_walls[sr][sc] = False
            new_maze.v_walls[sr][sc + 1] = False
            self._maze = new_maze
            self.log(f"Generated random maze {rows}x{cols} (density={density:.2f}).")

        self._rows_var.set(str(rows))
        self._cols_var.set(str(cols))
        self._update_start_goal_entries()
        self._redraw()

    def _on_clear_walls(self) -> None:
        self._maze = GridMaze(self._maze.rows, self._maze.cols)
        self._path_result = None
        self._redraw()

    def _load_presets(self) -> None:
        self._presets = load_maze_presets_with_names(_CONFIG)
        names = [v[0] for v in self._presets.values()]
        self._preset_cb.configure(values=names or ["—"])
        if names:
            self._preset_cb.set(names[0])
            first = next(iter(self._presets.values()))
            self._apply_maze_to_ui(first[1])

    def _on_load_preset(self, label: str) -> None:
        for name, maze in self._presets.values():
            if name == label:
                self._apply_maze_to_ui(maze)
                return

    def _on_save_preset(self) -> None:
        dlg = ctk.CTkInputDialog(text="Preset name:", title="Save Preset")
        name = dlg.get_input()
        if not name:
            return
        key = re.sub(r"\W+", "_", name.lower())
        self._presets[key] = (name, self._maze.clone())
        save_maze_presets(_CONFIG, {k: v[1] for k, v in self._presets.items()}, {k: v[0] for k, v in self._presets.items()})
        self._preset_cb.configure(values=[v[0] for v in self._presets.values()])
        self._preset_cb.set(name)

    def _on_solve(self) -> None:
        algo_name = self._solve_algo_var.get()
        algo_fn = ALGORITHMS.get(algo_name)
        if algo_fn is None:
            return
        self._path_result = algo_fn(self._maze)
        r = self._path_result
        if r.found:
            self._solve_info.configure(
                text=f"✓ {algo_name}\nPath: {r.path_length} steps\nExplored: {r.explored_count} cells\nTime: {r.time_ms:.3f} ms",
                text_color=_SB_ACCENT2
            )
        else:
            self._solve_info.configure(
                text=f"✗ {algo_name}\nNo path found!\nExplored: {r.explored_count} cells",
                text_color=_SB_DANGER
            )
        self._redraw()

    def _on_clear_path(self) -> None:
        self._path_result = None
        self._solve_info.configure(text="")
        self._redraw()

    def _apply_maze_to_ui(self, maze: GridMaze) -> None:
        self._maze = maze.clone()
        self._path_result = None
        self._rows_var.set(str(self._maze.rows))
        self._cols_var.set(str(self._maze.cols))
        self._update_start_goal_entries()
        self._redraw()

    def _on_apply_maze(self) -> None:
        if not self.robot.connected:
            return
        try:
            cs = float(self._cell_m.get())
        except ValueError:
            cs = 0.5
        self._cell_size_m = cs
        try:
            setup_grid_maze(self.robot.sim, self._maze, cell_size=cs)
        except Exception:
            pass

    def _on_clear_scene(self) -> None:
        if self.robot.connected:
            try:
                clear_grid_maze(self.robot.sim)
            except Exception:
                pass

    def _on_connect(self) -> None:
        if self.robot.connected:
            self.robot.disconnect()
            self._conn_lbl.configure(text=" Disconnected", text_color=_SB_MUTED)
            self._conn_dot.configure(text_color=_SB_DANGER)
            self._conn_btn.configure(text="Connect", fg_color=_SB_ACCENT)
        else:
            host = self._host.get().strip() or "localhost"
            try:
                port = int(self._port.get().strip())
            except ValueError:
                port = 23000
            try:
                self.robot.connect(host, port)
                self._conn_lbl.configure(text=" Connected", text_color=_SB_ACCENT2)
                self._conn_dot.configure(text_color=_SB_ACCENT2)
                self._conn_btn.configure(text="Disconnect", fg_color="#7f1d1d")
            except Exception:
                pass

    def _rebuild_learning_params(self) -> None:
        for w in self._params_frame.winfo_children():
            w.destroy()
        self._param_sliders.clear()
        for p in QLearningBehavior(self.robot).get_param_defs():
            row = ctk.CTkFrame(self._params_frame, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=p["label"], width=140, anchor="w", text_color=_SB_MUTED, font=ctk.CTkFont(size=11)).pack(side="left")
            vl = ctk.CTkLabel(row, text=f"{p['default']:.2f}", width=46, text_color=_SB_TEXT, font=ctk.CTkFont(size=11))
            sl = ctk.CTkSlider(
                row, from_=p["min"], to=p["max"],
                button_color=_SB_ACCENT, progress_color=_SB_ACCENT,
                command=lambda v, l=vl: l.configure(text=f"{v:.2f}")
            )
            sl.set(p["default"])
            sl.pack(side="left", fill="x", expand=True, padx=4)
            vl.pack(side="left")
            self._param_sliders[p["name"]] = sl

    def _on_start_beh(self) -> None:
        if not self.robot.connected:
            return
        try:
            self.robot.load_robot()
        except Exception:
            return
        beh = QLearningBehavior(self.robot)
        mapping = {"Q-learning": 0, "SARSA": 1, "Expected SARSA": 2, "Dyna-Q": 3}
        beh.algo = mapping.get(self._algo_var.get(), 0)
        for name, sl in self._param_sliders.items():
            beh.set_param(name, sl.get())
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._run_beh, args=(beh,), daemon=True)
        self._worker.start()
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")

    def _on_stop_beh(self) -> None:
        self._stop_event.set()

    def _run_beh(self, beh: BehaviorBase) -> None:
        try:
            self.robot.start_simulation()
            cell_sz = float(self._cell_m.get())
            goal_x, goal_y = self._maze.cell_world_pos(*self._maze.goal, cell_sz)
            while not self._stop_event.is_set():
                sensors = self.robot.read_sensors()
                pos = self.robot.get_position()
                vl, vr = beh.step(sensors, pos=pos)
                self.robot.set_velocity(vl, vr)
                if pos and len(pos) >= 2:
                    if math.hypot(pos[0] - goal_x, pos[1] - goal_y) < (cell_sz * 0.4):
                        if hasattr(beh, "_episode"):
                            beh._episode += 1
                        self.robot.set_velocity(0.0, 0.0)
                        self.robot.stop_simulation()
                        time.sleep(0.1)
                        self.robot.start_simulation()
                        continue
                try:
                    self._q.put_nowait({"type": "tick", "status": beh.get_status(), "vl": vl, "vr": vr, "sensors": sensors, "pos": pos})
                except queue.Full:
                    pass
                time.sleep(DT)
        except Exception:
            pass
        finally:
            try:
                self.robot.set_velocity(0.0, 0.0)
                self.robot.stop_simulation()
            except Exception:
                pass
            try:
                self._q.put_nowait({"type": "stopped"})
            except queue.Full:
                pass

    def _on_run_classical(self) -> None:
        self._classical_output.configure(state="normal")
        self._classical_output.delete("1.0", "end")
        header = f"{'Algorithm':<18} {'Found':>6} {'Steps':>6} {'Explored':>9} {'Time(ms)':>10}\n"
        self._classical_output.insert("end", header)
        self._classical_output.insert("end", "─" * 54 + "\n")

        best_steps = None
        rows_data = []
        for name, fn in ALGORITHMS.items():
            result = fn(self._maze)
            rows_data.append((name, result))
            if result.found and (best_steps is None or result.path_length < best_steps):
                best_steps = result.path_length

        for name, r in rows_data:
            if r.found:
                marker = " ★" if r.path_length == best_steps else ""
                line = f"{name:<18} {'YES':>6} {r.path_length:>6} {r.explored_count:>9} {r.time_ms:>9.3f}{marker}\n"
            else:
                line = f"{name:<18} {'NO':>6} {'—':>6} {r.explored_count:>9} {r.time_ms:>9.3f}\n"
            self._classical_output.insert("end", line)

        self._classical_output.insert("end", "\n★ = shortest path\n")
        self._classical_output.configure(state="disabled")

    def _on_run_compare(self) -> None:
        try:
            eps = int(self._exp_episodes.get())
        except Exception:
            eps = 50
        self._stop_event.clear()
        self._btn_bench.configure(state="disabled")
        threading.Thread(target=self._run_compare_worker, args=(eps,), daemon=True).start()

    def _run_compare_worker(self, episodes: int) -> None:
        import io
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        self._append_exp_output(f"Running {episodes} episodes per algorithm on current maze...\n")

        env = GridEnv(self._maze)
        all_results: dict[str, list] = {}

        for name, runner in RUNNERS.items():
            if self._stop_event.is_set():
                break
            self._append_exp_output(f"  [{name}] ...")
            data = runner(env, episodes)
            all_results[name] = data
            solved = sum(1 for _, _, ok in data if ok)
            avg_steps = sum(s for _, s, ok in data if ok) / max(1, solved)
            last_10_r = sum(r for r, _, _ in data[-10:]) / 10
            self._append_exp_output(
                f"  [{name}] solved {solved}/{episodes} eps  "
                f"avg_steps={avg_steps:.1f}  last10_reward={last_10_r:.1f}"
            )

        if self._stop_event.is_set():
            self._append_exp_output("\n[STOPPED]")
            self._btn_bench.configure(state="normal")
            return

        # ── Summary table ───────────────────────────────────────────
        self._append_exp_output("\n" + "─" * 62)
        self._append_exp_output(
            f"{'Algorithm':<16} {'Solved':>7} {'Solve%':>7} "
            f"{'AvgSteps':>9} {'BestRew':>9}"
        )
        self._append_exp_output("─" * 62)
        for name, data in all_results.items():
            solved = sum(1 for _, _, ok in data if ok)
            pct = solved / episodes * 100
            avg_s = sum(s for _, s, ok in data if ok) / max(1, solved)
            best_r = max(r for r, _, _ in data)
            self._append_exp_output(
                f"{name:<16} {solved:>7} {pct:>6.1f}% "
                f"{avg_s:>9.1f} {best_r:>9.1f}"
            )
        self._append_exp_output("─" * 62)

        # ── Chart ───────────────────────────────────────────────────
        colors = ["#3b82f6", "#34d399", "#fbbf24", "#a78bfa"]

        def smooth(vals, w=6):
            out = []
            for i in range(len(vals)):
                sl = vals[max(0, i - w): i + w + 1]
                out.append(sum(sl) / len(sl))
            return out

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4),
                                        facecolor="#0f1923")
        for ax in (ax1, ax2):
            ax.set_facecolor("#162032")
            for sp in ax.spines.values():
                sp.set_edgecolor("#1e3a5c")
            ax.tick_params(colors="#94a3b8", labelsize=9)
            ax.xaxis.label.set_color("#94a3b8")
            ax.yaxis.label.set_color("#94a3b8")
            ax.title.set_color("#e2e8f0")
            ax.grid(color="#1e3a5c", linestyle="--", linewidth=0.5, alpha=0.8)

        eps_x = list(range(1, episodes + 1))
        for (name, data), col in zip(all_results.items(), colors):
            rewards = [r for r, _, _ in data]
            ax1.plot(eps_x, smooth(rewards), color=col, lw=2, label=name)

        ax1.set_xlabel("Episod")
        ax1.set_ylabel("Recompensă totală")
        ax1.set_title("Recompensă per episod (smoothed)")
        ax1.legend(fontsize=8, facecolor="#162032", edgecolor="#1e3a5c",
                   labelcolor="#e2e8f0")

        window = max(1, episodes // 10)
        for (name, data), col in zip(all_results.items(), colors):
            rates = []
            for i in range(len(data)):
                sl = data[max(0, i - window): i + 1]
                rates.append(sum(1 for _, _, ok in sl if ok) / len(sl) * 100)
            ax2.plot(eps_x, rates, color=col, lw=2, label=name)

        ax2.set_xlabel("Episod")
        ax2.set_ylabel("Rată rezolvare (%)")
        ax2.set_title("Rată succes (fereastră mobilă)")
        ax2.set_ylim(0, 105)
        ax2.legend(fontsize=8, facecolor="#162032", edgecolor="#1e3a5c",
                   labelcolor="#e2e8f0")

        fig.tight_layout(pad=1.2)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                    facecolor="#0f1923")
        plt.close(fig)
        buf.seek(0)

        from PIL import Image as PILImage
        pil_img = PILImage.open(buf)
        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img,
                               size=(pil_img.width // 2, pil_img.height // 2))

        self._bench_chart_lbl.configure(image=ctk_img, text="")
        self._bench_chart_lbl._image = ctk_img  # keep reference

        self._append_exp_output("\n[DONE] Benchmark finalizat.")
        self._btn_bench.configure(state="normal")

    def _append_exp_output(self, text: str) -> None:
        try:
            self._exp_output.configure(state="normal")
            self._exp_output.insert("end", text + "\n")
            self._exp_output.see("end")
            self._exp_output.configure(state="disabled")
        except Exception:
            pass

    def _update_sensors(self, sensors: list[SensorReading], pos: tuple) -> None:
        for bar, lbl, s in zip(self._sbars, self._sdist, sensors):
            if s.detected:
                bar.set(max(0.0, min(1.0, 1.0 - s.distance)))
                lbl.configure(text=f"{s.distance:.2f}m")
            else:
                bar.set(0.0)
                lbl.configure(text="---")
        if pos and len(pos) >= 2:
            self._pos_lbl.configure(text=f"Pos: X={pos[0]:.2f}  Y={pos[1]:.2f}")

    def _poll(self) -> None:
        try:
            while True:
                msg = self._q.get_nowait()
                if msg["type"] == "tick":
                    self._beh_status.configure(text=f"Agent Status: {msg['status']}")
                    self._vel_lbl.configure(text=f"Motors: vL = {msg['vl']:+.2f}  ·  vR = {msg['vr']:+.2f}")
                    if self._auto_refresh.get():
                        self._update_sensors(msg["sensors"], msg["pos"])
                elif msg["type"] == "stopped":
                    self._start_btn.configure(state="normal")
                    self._stop_btn.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def log(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"[{ts}]  {msg}\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")


# ── Helper widgets ────────────────────────────────────────────────────

def _card(parent, border_color: str = "#1e3a5c") -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=_SB_CARD, corner_radius=10, border_width=1, border_color=border_color)


def _divider(parent, color: str = "#1e3a5c") -> None:
    ctk.CTkFrame(parent, height=1, fg_color=color).pack(fill="x", padx=10, pady=8)


def _section_label(parent, text: str) -> None:
    ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=9, weight="bold"),
        text_color=_SB_MUTED
    ).pack(anchor="w", padx=14, pady=(10, 2))


def _primary_btn(parent, text: str, command, color: str = _SB_ACCENT) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=command,
        fg_color=color, hover_color="#2563eb",
        corner_radius=8, height=34,
        font=ctk.CTkFont(size=12, weight="bold")
    )


def _ghost_btn(parent, text: str, command) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=command,
        fg_color="transparent", hover_color="#1a2d47",
        border_width=1, border_color=_SB_CARD_B,
        text_color=_SB_MUTED, corner_radius=8, height=34,
        font=ctk.CTkFont(size=12)
    )


def _page_header(parent, title: str, subtitle: str = "") -> None:
    ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=22, weight="bold"), text_color=_SB_TEXT).pack(anchor="w", pady=(0, 2))
    if subtitle:
        ctk.CTkLabel(parent, text=subtitle, font=ctk.CTkFont(size=12), text_color=_SB_MUTED).pack(anchor="w", pady=(0, 14))


def _draw_marker(canvas: tk.Canvas, cx: float, cy: float, r: float, color: str, label: str) -> None:
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="white", width=1)
    canvas.create_text(cx, cy, text=label, fill="white", font=("Arial", max(8, int(r * 1.1)), "bold"))


def _set_entry(e: ctk.CTkEntry, v: str) -> None:
    e.delete(0, "end")
    e.insert(0, v)

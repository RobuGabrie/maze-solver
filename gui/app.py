"""
gui/app.py - Interfață Dashboard Cyberpunk cu Modul de Benchmarking Separat
Implementează design Sidebar Navigation, Cerințe Echipă și Taburi de Lucru Dedicate.
"""
import datetime
import math
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path

from pathlib import Path
from PIL import Image, ImageOps

import customtkinter as ctk
try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

from core.behaviors import QLearningBehavior, SENSOR_LABELS, BehaviorBase, DT
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

# ── căi fișiere ───────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
_CONFIG = _ROOT / "config" / "mazes.json"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── paletă culori neon-cyberpunk pentru vizualizarea labirintului ──
_C_BG        = "#06060c"  # Fundal canvas foarte închis
_C_CELL      = "#0d0d1a"  # Interiorul unei celule libere
_C_EXPLORED  = "#1a103c"  # Spațiu explorat de algoritmul AI
_C_PATH      = "#39ff14"  # Traseu optim generat (Verde Neon)
_C_START     = "#00ffff"  # Start (Cyan Neon)
_C_GOAL      = "#ff007f"  # Goal (Roz/Magenta Neon)
_C_WALL      = "#ff3131"  # Pereți interni (Roșu Neon)
_C_BOUNDARY  = "#00f5ff"  # Pereți exteriori (Cyan închis)
_C_ROBOT     = "#fffb00"  # Robotul (Galben Neon)

_MARGIN = 20   


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AI Maze Simulator & Benchmarker v3.0")
        self.geometry("1300x820")
        self.minsize(1155, 720)

        # Core backend engine
        self.robot = Robot()
        self._maze: GridMaze = GridMaze(7, 7)
        self._presets: dict[str, tuple[str, GridMaze]] = {}   
        self._cell_size_m: float = 0.5
        self._mobiles: list[dict] = []
        self._selected_mobile: int | None = None
        self._placing_mobile: bool = False
        self._adding_waypoint: bool = False
        self._hover_cell: tuple[int, int] | None = None

        # Threading workers
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._q: queue.Queue = queue.Queue(maxsize=10)

        # Variabile UI securizate (Evită erorile Tcl de string gol)
        self._rows_var = ctk.StringVar(value="7")
        self._cols_var = ctk.StringVar(value="7")
        self._exp_episodes = ctk.StringVar(value="50")

        # Construire ecran și structură taburi în Sidebar
        self._build_main_layout()
        self._load_presets()
        self._poll()

        # Pornire implicită pe Pagina de Start
        self._select_menu("home")

    # ══════════════════════════════════════════════════════════════
    # Structură Principală (Sidebar + Spaiu de Conținut)
    # ══════════════════════════════════════════════════════════════

    def _build_main_layout(self) -> None:
        # 1. Sidebar Frame (Meniu Lateral)
        self._sidebar = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color="#0a0a14")
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        # Identitate proiect în Meniu
        lbl_title = ctk.CTkLabel(self._sidebar, text="Patanii", font=ctk.CTkFont(size=22, weight="bold"), text_color="#00ffff")
        lbl_title.pack(pady=(25, 5), padx=20, anchor="w")
        lbl_subtitle = ctk.CTkLabel(self._sidebar, text="AI Benchmarking Engine", font=ctk.CTkFont(size=12), text_color="gray50")
        lbl_subtitle.pack(pady=(0, 25), padx=20, anchor="w")

        # Butoane Navigare Meniu (Tabul de Benchmark acum este complet separat)
        self._menu_btns = {}
        menu_specs = [
            ("home", "🏠  Pagină de Start"),
            ("doc", "📚  Concept & Algoritmi"),
            ("maze", "🧱  Editor Labirint Visual"),
            ("train", "⚡  Antrenare Agent"),
            ("bench", "📊  Modul Benchmarking"),
            ("monitor", "🖥️  Monitorizare Senzori")
        ]
        for key, text in menu_specs:
            btn = ctk.CTkButton(
                self._sidebar, text=text, anchor="w", height=42,
                fg_color="transparent", text_color="gray80", hover_color="#1a103c",
                command=lambda k=key: self._select_menu(k)
            )
            btn.pack(fill="x", padx=12, pady=4)
            self._menu_btns[key] = btn

        # Zona inferioară din sidebar dedicată conexiunii cu simulatorul CoppeliaSim
        _sep(self._sidebar)
        conn_frame = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        conn_frame.pack(side="bottom", fill="x", padx=10, pady=15)
        
        ctk.CTkLabel(conn_frame, text="CoppeliaSim Connection", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray50").pack(anchor="w", padx=5)
        self._host = ctk.CTkEntry(conn_frame, placeholder_text="localhost", height=28)
        self._host.insert(0, "localhost")
        self._host.pack(fill="x", pady=2, padx=5)
        
        self._port = ctk.CTkEntry(conn_frame, placeholder_text="23000", height=28)
        self._port.insert(0, "23000")
        self._port.pack(fill="x", pady=2, padx=5)

        self._conn_btn = ctk.CTkButton(conn_frame, text="Conectare", height=32, fg_color="#1f6aa5", command=self._on_connect)
        self._conn_btn.pack(fill="x", pady=(5, 2), padx=5)
        self._conn_lbl = ctk.CTkLabel(conn_frame, text="● Deconectat", text_color="#ff3131", font=ctk.CTkFont(size=12, weight="bold"))
        self._conn_lbl.pack(pady=2)

        # 2. Main Content Frame Container
        self._content_container = ctk.CTkFrame(self, fg_color="#020205", corner_radius=0)
        self._content_container.pack(side="left", fill="both", expand=True)

        # Alocare pagini în container
        self._pages = {
            "home": ctk.CTkScrollableFrame(self._content_container, fg_color="transparent"),
            "doc": ctk.CTkScrollableFrame(self._content_container, fg_color="transparent"),
            "maze": ctk.CTkFrame(self._content_container, fg_color="transparent"),
            "train": ctk.CTkFrame(self._content_container, fg_color="transparent"),
            "bench": ctk.CTkFrame(self._content_container, fg_color="transparent"),
            "monitor": ctk.CTkFrame(self._content_container, fg_color="transparent")
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
            self._menu_btns[key].configure(fg_color="transparent", text_color="gray80")
        
        self._pages[target_key].pack(fill="both", expand=True, padx=15, pady=15)
        self._menu_btns[target_key].configure(fg_color="#1a103c", text_color="#00ffff", border_width=1, border_color="#00ffff")
        if target_key == "maze" or target_key == "train":
            self._redraw()

    # ══════════════════════════════════════════════════════════════
    # 1. Pagină de Start (Home)
    # ══════════════════════════════════════════════════════════════

    def _build_home_page(self, parent: ctk.CTkScrollableFrame) -> None:
        header = ctk.CTkFrame(parent, fg_color="#0a0a1a", corner_radius=12, border_width=1, border_color="#1a103c")
        header.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(header, text="PROIECT DILEMA / DISCIPLINĂ APLICATĂ", font=ctk.CTkFont(size=12, weight="bold"), text_color="#00ffff").pack(anchor="w", padx=20, pady=(15, 2))
        ctk.CTkLabel(header, text="Aplicație Autonomă de Navigație și Benchmark RL", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=20, pady=(0, 5))
        ctk.CTkLabel(header, text="Disciplina: Inteligență Artificială  |  Anul Universitar: 2026", font=ctk.CTkFont(size=14), text_color="gray60").pack(anchor="w", padx=20, pady=(0, 15))

        team_section = ctk.CTkFrame(parent, fg_color="transparent")
        team_section.pack(fill="x", pady=10)
        
        ctk.CTkLabel(team_section, text="Componența Echipei: Patanii", font=ctk.CTkFont(size=16, weight="bold"), text_color="#ff007f").pack(anchor="w", pady=(0, 10))
        cards_frame = ctk.CTkFrame(team_section, fg_color="transparent")
        cards_frame.pack(fill="x")
        
        # --- CONFIGURARE MEMBRI ȘI FIȘIERE JPEG ---
        membri_detalii = [
            {"nume": "Rusu Sebastian", "foto": "C:\\Users\\Sebastian\\Desktop\\IA_Echipa_Patanii-sim\\IA_Echipa_Patanii-sim\\RusuS.jpeg"},
            {"nume": "Casciuc Stanislav", "foto": "C:\\Users\\Sebastian\\Desktop\\IA_Echipa_Patanii-sim\\IA_Echipa_Patanii-sim\\CasciucS.jpeg"},
            {"nume": "Robu Gabriel", "foto": "C:\\Users\\Sebastian\\Desktop\\IA_Echipa_Patanii-sim\\IA_Echipa_Patanii-sim\\RobuG.jpeg"}
        ]
        
        for membru in membri_detalii:
            nume = membru["nume"]
            nume_foto = membru["foto"]
            
            # Creare card
            card = ctk.CTkFrame(cards_frame, fg_color="#0a0a16", width=225, height=250, corner_radius=10, border_width=1, border_color="#1a103c")
            card.pack(side="left", padx=(0, 15), pady=5)
            card.pack_propagate(False)
            
            # Calea către imaginea din folderul config
            img_path = _ROOT / "config" / nume_foto
            loaded_img = False
            
            if _PIL_OK and img_path.exists():
                try:
                    img_obj = Image.open(img_path)
                    
                    # Decupare automată pătrată (crop central din PIL) pentru a preveni distorsiunea
                    latime, inaltime = img_obj.size
                    min_dim = min(latime, inaltime)
                    img_obj = ImageOps.fit(img_obj, (min_dim, min_dim), Image.Resampling.LANCZOS)
                    
                    # Redimensionare la 130x130
                    img_obj = img_obj.resize((130, 130), Image.Resampling.LANCZOS)
                    
                    ctk_img = ctk.CTkImage(light_image=img_obj, dark_image=img_obj, size=(130, 130))
                    ctk.CTkLabel(card, image=ctk_img, text="").pack(pady=15)
                    loaded_img = True
                except Exception:
                    pass
            
            # Avatar implicit dacă imaginea JPEG nu este găsită pe disc
            if not loaded_img:
                lbl_box = ctk.CTkFrame(card, width=130, height=130, fg_color="#161630", corner_radius=10)
                lbl_box.pack(pady=15)
                lbl_box.pack_propagate(False)
                ctk.CTkLabel(lbl_box, text="👤", font=ctk.CTkFont(size=48)).pack(expand=True)
                
            # Detalii text
            ctk.CTkLabel(card, text=nume, font=ctk.CTkFont(size=13, weight="bold"), wraplength=190).pack(pady=5)
            ctk.CTkLabel(card, text="Developer / AI Research", font=ctk.CTkFont(size=11), text_color="gray50").pack()
        
    # ══════════════════════════════════════════════════════════════
    # 2. Pagină Documentație
    # ══════════════════════════════════════════════════════════════

    def _build_doc_page(self, parent: ctk.CTkScrollableFrame) -> None:
        f_robot = ctk.CTkFrame(parent, fg_color="#0a0a1a", corner_radius=12)
        f_robot.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(f_robot, text="🤖 Cum Funcționează Robotul (Virtual / Real)", font=ctk.CTkFont(size=16, weight="bold"), text_color="#ff007f").pack(anchor="w", padx=20, pady=(15, 5))
        desc_robot = (
            "• Capabilități Senzoriale: Robotul utilizează un array circular format din 16 senzori independenți de proximitate.\n"
            "• Control: Deplasarea autonomă este determinată cinemati prin ajustarea vitezei roților vL și vR.\n"
            "• Scopul: Identificarea traseului minim și ocolirea barierelor dinamice din labirint până la destinație."
        )
        ctk.CTkLabel(f_robot, text=desc_robot, font=ctk.CTkFont(size=13), justify="left", wraplength=760, text_color="gray85").pack(anchor="w", padx=20, pady=(0, 15))

        f_ai = ctk.CTkFrame(parent, fg_color="#0a0a1a", corner_radius=12)
        f_ai.pack(fill="x", pady=10)
        ctk.CTkLabel(f_ai, text="🧠 Arhitectura Inteligenței Artificiale (Algoritmi RL)", font=ctk.CTkFont(size=16, weight="bold"), text_color="#00ffff").pack(anchor="w", padx=20, pady=(15, 5))
        desc_ai = (
            "Platforma integrează 4 abordări majore din Reinforcement Learning:\n"
            "1. Q-Learning (Off-Policy Temporal Difference)\n"
            "2. SARSA (On-Policy State-Action-Reward-State-Action)\n"
            "3. Expected SARSA (Actualizare stabilă prin calculul valorii medii a acțiunilor viitoare)\n"
            "4. Dyna-Q (Combină învățarea directă din mediu cu generarea de episoade imaginate pentru planificare rapidă)"
        )
        ctk.CTkLabel(f_ai, text=desc_ai, font=ctk.CTkFont(size=13), justify="left", wraplength=760, text_color="gray85").pack(anchor="w", padx=20, pady=(0, 15))

    # ══════════════════════════════════════════════════════════════
    # 3. Pagină Labirint Vizual Redesenat (Aspect Neon Cyberpunk)
    # ══════════════════════════════════════════════════════════════

    def _build_maze_page(self, parent: ctk.CTkFrame) -> None:
        # Control Sidebar pentru Editor stânga
        left_ctrl = ctk.CTkFrame(parent, width=280, fg_color="#0a0a16", border_width=1, border_color="#1a103c")
        left_ctrl.pack(side="left", fill="y", padx=(0, 10), pady=5)
        left_ctrl.pack_propagate(False)

        # ── Secțiunea 1: Dimensiune Grid ──────────────────────────────
        ctk.CTkLabel(left_ctrl, text="Dimensiune Grid", font=ctk.CTkFont(weight="bold", size=14), text_color="#00ffff").pack(anchor="w", padx=15, pady=(15, 4))
        
        r_box = ctk.CTkFrame(left_ctrl, fg_color="transparent")
        r_box.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(r_box, text="Rânduri:", width=80, anchor="w").pack(side="left")
        ctk.CTkEntry(r_box, textvariable=self._rows_var, width=70).pack(side="left")

        c_box = ctk.CTkFrame(left_ctrl, fg_color="transparent")
        c_box.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(c_box, text="Coloane:", width=80, anchor="w").pack(side="left")
        ctk.CTkEntry(c_box, textvariable=self._cols_var, width=70).pack(side="left")
        
        ctk.CTkButton(left_ctrl, text="Aplică Dimensiune", command=self._on_resize, fg_color="#1a103c", border_width=1, border_color="#00ffff").pack(fill="x", padx=15, pady=8)

        _sep(left_ctrl)

        # ── Secțiunea 2: Noduri Start / Goal ───────────────────────────
        ctk.CTkLabel(left_ctrl, text="Noduri Start / Goal", font=ctk.CTkFont(weight="bold", size=13), text_color="#ff007f").pack(anchor="w", padx=15, pady=(4, 2))
        
        sg1 = ctk.CTkFrame(left_ctrl, fg_color="transparent")
        sg1.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(sg1, text="Start R:", width=50).pack(side="left")
        self._start_r = ctk.CTkEntry(sg1, width=45)
        self._start_r.insert(0, "0")
        self._start_r.pack(side="left", padx=2)
        ctk.CTkLabel(sg1, text="C:").pack(side="left", padx=2)
        self._start_c = ctk.CTkEntry(sg1, width=45)
        self._start_c.insert(0, "0")
        self._start_c.pack(side="left")

        sg2 = ctk.CTkFrame(left_ctrl, fg_color="transparent")
        sg2.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(sg2, text="Goal R:", width=50).pack(side="left")
        self._goal_r = ctk.CTkEntry(sg2, width=45)
        self._goal_r.insert(0, "6")
        self._goal_r.pack(side="left", padx=2)
        ctk.CTkLabel(sg2, text="C:").pack(side="left", padx=2)
        self._goal_c = ctk.CTkEntry(sg2, width=45)
        self._goal_c.insert(0, "6")
        self._goal_c.pack(side="left")

        ctk.CTkButton(left_ctrl, text="Setează Start/Goal", command=self._on_set_start_goal, fg_color="#1a103c").pack(fill="x", padx=15, pady=6)

        _sep(left_ctrl)

        # ── Secțiunea 3: Instrumente Labirint (Noua Configurație) ──
        ctk.CTkLabel(left_ctrl, text="Instrumente Labirint", font=ctk.CTkFont(weight="bold", size=13), text_color="#00ffff").pack(anchor="w", padx=15, pady=(4, 2))
        
        # Meniu Dropdown pentru selectarea modului de generare
        self._gen_type_var = ctk.StringVar(value="Perfect (DFS)")
        self._gen_type_cb = ctk.CTkComboBox(left_ctrl, values=["Perfect (DFS)", "Aleatoriu (Densitate)"], variable=self._gen_type_var)
        self._gen_type_cb.pack(fill="x", padx=15, pady=3)
        
        # Slider dedicat pentru controlul densității în cazul modului aleatoriu
        density_frame = ctk.CTkFrame(left_ctrl, fg_color="transparent")
        density_frame.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(density_frame, text="Densitate:", width=65, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left")
        self._density_slider = ctk.CTkSlider(density_frame, from_=0.1, to=0.6, number_of_steps=10)
        self._density_slider.set(0.25)
        self._density_slider.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(left_ctrl, text="Generează Labirint", command=self._on_generate, fg_color="#1f6aa5", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=15, pady=5)
        ctk.CTkButton(left_ctrl, text="Șterge Toți Pereții", command=self._on_clear_walls, fg_color="#333344").pack(fill="x", padx=15, pady=3)

        _sep(left_ctrl)

        # ── Secțiunea 4: Salvare / Încărcare Presets ───────────────────
        ctk.CTkLabel(left_ctrl, text="Salvare Presets", font=ctk.CTkFont(weight="bold", size=13)).pack(anchor="w", padx=15, pady=2)
        self._preset_cb = ctk.CTkComboBox(left_ctrl, command=self._on_load_preset)
        self._preset_cb.pack(fill="x", padx=15, pady=3)
        ctk.CTkButton(left_ctrl, text="Salvează Preset", command=self._on_save_preset, fg_color="#2e6f40").pack(fill="x", padx=15, pady=3)

        # ── Zona Canvas-ului Centrală (Design Neon Cyberpunk) ───────────
        center_canvas = ctk.CTkFrame(parent, fg_color="#030308")
        center_canvas.pack(side="left", fill="both", expand=True, pady=5)
        
        info_hint = ctk.CTkLabel(center_canvas, text="💡 Click stânga: Adaugă/Șterge Pereți | Click dreapta în celulă: Mută Start/Goal", font=ctk.CTkFont(size=11), text_color="gray50")
        info_hint.pack(pady=4)

        self._canvas = tk.Canvas(center_canvas, bg=_C_BG, highlightthickness=1, highlightbackground="#1a103c")
        self._canvas.pack(fill="both", expand=True, padx=15, pady=15)
        self._canvas.bind("<Configure>", lambda _: self._redraw())
        self._canvas.bind("<Button-1>", self._on_canvas_left)
        self._canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self._canvas.bind("<Button-3>", self._on_canvas_right)

    # ══════════════════════════════════════════════════════════════
    # 4. Pagină de Antrenare Instanță Unică
    # ══════════════════════════════════════════════════════════════

    def _build_train_page(self, parent: ctk.CTkFrame) -> None:
        left_p = ctk.CTkFrame(parent, width=340, fg_color="#0a0a16", border_width=1, border_color="#1a103c")
        left_p.pack(side="left", fill="y", padx=(0, 10), pady=5)
        left_p.pack_propagate(False)

        ctk.CTkLabel(left_p, text="Selectare Algoritm", font=ctk.CTkFont(size=14, weight="bold"), text_color="#00ffff").pack(anchor="w", padx=15, pady=(15, 5))
        self._algo_var = ctk.StringVar(value="Q-learning")
        self._algo_selector = ctk.CTkOptionMenu(left_p, values=["Q-learning", "SARSA", "Expected SARSA", "Dyna-Q"], variable=self._algo_var)
        self._algo_selector.pack(fill="x", padx=15, pady=5)

        self._params_frame = ctk.CTkScrollableFrame(left_p, label_text="Hiperparametri Model", fg_color="transparent")
        self._params_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self._param_sliders: dict[str, ctk.CTkSlider] = {}
        self._param_val_lbls: dict[str, ctk.CTkLabel] = {}
        self._rebuild_learning_params()

        right_p = ctk.CTkFrame(parent, fg_color="#050510")
        right_p.pack(side="left", fill="both", expand=True, pady=5)

        ctk.CTkLabel(right_p, text="Simulare Interfață Virtuală", font=ctk.CTkFont(size=16, weight="bold"), text_color="#ff007f").pack(anchor="w", padx=20, pady=15)
        
        box_sim = ctk.CTkFrame(right_p, fg_color="#0c0c20")
        box_sim.pack(fill="x", padx=20, pady=10)
        csz = ctk.CTkFrame(box_sim, fg_color="transparent")
        csz.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(csz, text="Dimensiune Celulă Simulare (m):").pack(side="left")
        self._cell_m = ctk.CTkEntry(csz, width=70)
        self._cell_m.insert(0, "0.5")
        self._cell_m.pack(side="left", padx=10)

        ctk.CTkButton(box_sim, text="Sincronizează Labirintul în CoppeliaSim", fg_color="#1f6aa5", height=38, command=self._on_apply_maze).pack(fill="x", padx=15, pady=5)
        ctk.CTkButton(box_sim, text="Golește Scena CoppeliaSim", fg_color="#444", height=34, command=self._on_clear_scene).pack(fill="x", padx=15, pady=(5, 15))

        box_exec = ctk.CTkFrame(right_p, fg_color="#0c0c20")
        box_exec.pack(fill="both", expand=True, padx=20, pady=(10, 15))
        ctk.CTkLabel(box_exec, text="Execuție Instanță Controler", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=15, pady=10)
        
        ctrl_b = ctk.CTkFrame(box_exec, fg_color="transparent")
        ctrl_b.pack(fill="x", padx=15, pady=5)
        self._start_btn = ctk.CTkButton(ctrl_b, text="▶  Pornește Antrenare", fg_color="#2e6f40", height=42, command=self._on_start_beh)
        self._start_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self._stop_btn = ctk.CTkButton(ctrl_b, text="■  Stop", fg_color="#7a2020", height=42, state="disabled", command=self._on_stop_beh)
        self._stop_btn.pack(side="left", padx=5)

        self._beh_status = ctk.CTkLabel(box_exec, text="Status Agent: Inactiv", font=ctk.CTkFont(size=13, weight="bold"), anchor="w")
        self._beh_status.pack(fill="x", padx=18, pady=5)
        self._vel_lbl = ctk.CTkLabel(box_exec, text="Viteze Motoare: vL = 0.00 | vR = 0.00", font=ctk.CTkFont(family="Courier", size=13), anchor="w")
        self._vel_lbl.pack(fill="x", padx=18, pady=5)

    # ══════════════════════════════════════════════════════════════
    # 5. TAB NOU SEPARAT: Modul Benchmarking Multi-Algoritm
    # ══════════════════════════════════════════════════════════════

    def _build_bench_page(self, parent: ctk.CTkFrame) -> None:
        # Layout complet pentru Tabul de Benchmark solicitat separat
        top_bar = ctk.CTkFrame(parent, fg_color="#0a0a1a", border_width=1, border_color="#1a103c")
        top_bar.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(top_bar, text="📊 Evaluare Comparativă și Benchmarking Algoritmi", font=ctk.CTkFont(size=16, weight="bold"), text_color="#00ffff").pack(side="left", padx=15, pady=15)
        
        param_b = ctk.CTkFrame(top_bar, fg_color="transparent")
        param_b.pack(side="right", padx=15, pady=10)
        ctk.CTkLabel(param_b, text="Episoade per Model: ", font=ctk.CTkFont(size=13)).pack(side="left")
        ctk.CTkEntry(param_b, textvariable=self._exp_episodes, width=70).pack(side="left", padx=5)
        
        self._btn_bench = ctk.CTkButton(param_b, text="⚡ Lansează Benchmark Complet", fg_color="#ff007f", font=ctk.CTkFont(weight="bold"), command=self._on_run_compare)
        self._btn_bench.pack(side="left", padx=10)

        # Zona centrală de afișare log performanțe
        body = ctk.CTkFrame(parent, fg_color="#05050f")
        body.pack(fill="both", expand=True)
        
        lbl_info = ctk.CTkLabel(body, text="Rezultatele rulării comparative (Q-Learning vs SARSA vs Expected SARSA vs Dyna-Q):", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray50")
        lbl_info.pack(anchor="w", padx=15, pady=(10, 5))
        
        self._exp_output = ctk.CTkTextbox(body, fg_color="#020206", font=ctk.CTkFont(family="Courier", size=12), state="disabled", border_width=1, border_color="#1a103c")
        self._exp_output.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    # ══════════════════════════════════════════════════════════════
    # 6. Pagină Monitorizare Senzori & Loguri
    # ══════════════════════════════════════════════════════════════

    def _build_monitor_page(self, parent: ctk.CTkFrame) -> None:
        f_sens = ctk.CTkFrame(parent, fg_color="#0a0a16")
        f_sens.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        top_s = ctk.CTkFrame(f_sens, fg_color="transparent")
        top_s.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top_s, text="Senzori Circular-Ultrasonici (16 Canale)", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self._auto_refresh = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(top_s, text="Live", variable=self._auto_refresh, width=60).pack(side="right", padx=5)
        self._pos_lbl = ctk.CTkLabel(top_s, text="Poziție: X=— Y=—")
        self._pos_lbl.pack(side="right", padx=10)

        scroll_s = ctk.CTkScrollableFrame(f_sens, fg_color="transparent")
        scroll_s.pack(fill="both", expand=True, padx=5, pady=2)
        
        self._sbars: list[ctk.CTkProgressBar] = []
        self._sdist: list[ctk.CTkLabel] = []
        for i, lbl in enumerate(SENSOR_LABELS):
            row = ctk.CTkFrame(scroll_s, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"[{i:02d}] {lbl}", width=140, anchor="w", font=ctk.CTkFont(family="Courier", size=11)).pack(side="left", padx=2)
            bar = ctk.CTkProgressBar(row, width=150, progress_color="#00ffff")
            bar.set(0)
            bar.pack(side="left", padx=4)
            dl = ctk.CTkLabel(row, text="---", width=60, anchor="w", font=ctk.CTkFont(family="Courier"))
            dl.pack(side="left", padx=2)
            self._sbars.append(bar)
            self._sdist.append(dl)

        f_log = ctk.CTkFrame(parent, width=420, fg_color="#0a0a16")
        f_log.pack(side="right", fill="y", padx=(5, 0))
        f_log.pack_propagate(False)
        ctk.CTkLabel(f_log, text="Jurnal Evenimente Sistem (Log)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        self._log_box = ctk.CTkTextbox(f_log, font=ctk.CTkFont(family="Courier", size=11), state="disabled", fg_color="#030308")
        self._log_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ══════════════════════════════════════════════════════════════
    # Logica de Redesenare și Click-uri (Corectată și Stilizată Neon)
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

        # 1. Desenare celule interioare cu rețea fină Cyberpunk
        for r in range(rows):
            for c in range(cols):
                x0 = ox + c * cp
                y0 = oy + r * cp
                canvas.create_rectangle(x0, y0, x0 + cp, y0 + cp, fill=_C_CELL, outline="#111126")

        # 2. Desenare noduri speciale Start și Goal
        sr, sc = m.start
        gr, gc = m.goal
        _draw_marker(canvas, ox + sc * cp + cp / 2, oy + sr * cp + cp / 2, cp * 0.35, _C_START, "S")
        _draw_marker(canvas, ox + gc * cp + cp / 2, oy + gr * cp + cp / 2, cp * 0.35, _C_GOAL, "G")

        # 3. Desenare pereți Orizontali
        for r in range(rows + 1):
            for c in range(cols):
                if m.h_walls[r][c]:
                    is_b = m.is_boundary_h(r)
                    color = _C_BOUNDARY if is_b else _C_WALL
                    w = 4 if is_b else 3
                    x0 = ox + c * cp
                    y0 = oy + r * cp
                    canvas.create_line(x0, y0, x0 + cp, y0, fill=color, width=w)

        # 4. Desenare pereți Verticali
        for r in range(rows):
            for c in range(cols + 1):
                if m.v_walls[r][c]:
                    is_b = m.is_boundary_v(c)
                    color = _C_BOUNDARY if is_b else _C_WALL
                    w = 4 if is_b else 3
                    x0 = ox + c * cp
                    y0 = oy + r * cp
                    canvas.create_line(x0, y0, x0, y0 + cp, fill=color, width=w)

        # 5. Randare poziție Live robot pe grilă
        if robot_pos:
            rr, rc = robot_pos
            if 0 <= rr < rows and 0 <= rc < cols:
                rad = max(5, cp * 0.28)
                canvas.create_oval(ox + rc * cp + cp / 2 - rad, oy + rr * cp + cp / 2 - rad,
                                   ox + rc * cp + cp / 2 + rad, oy + rr * cp + cp / 2 + rad,
                                   fill=_C_ROBOT, outline="white", width=1)

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
        if not hit: return
        wtype, wr, wc = hit
        if wtype == "h":
            self._maze.toggle_h_wall(wr, wc)
        else:
            self._maze.toggle_v_wall(wr, wc)
        self._last_toggled = hit
        self._redraw()

    def _on_canvas_drag(self, event: tk.Event) -> None:
        hit = self._hit_wall(event.x, event.y)
        if not hit or hit == self._last_toggled: return
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
        if not (0 <= r < self._maze.rows and 0 <= c < self._maze.cols): return
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
        except ValueError: return
        rows = _clamp(rows, 2, 25)
        cols = _clamp(cols, 2, 25)
        self._maze = GridMaze(rows, cols)
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
        except ValueError: return
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
            # Folosește algoritmul nativ importat din core.maze
            self._maze = generate_maze(rows, cols)
            self.log(f"Generat labirint perfect {rows}x{cols} (DFS).")
        else:
            # Generare aleatorie pe baza densității selectate
            import random
            new_maze = GridMaze(rows, cols)
            density = self._density_slider.get()
            
            # Generăm pereți interni orizontali (evităm marginile exterioare controlate de boundary)
            for r in range(1, rows):
                for c in range(cols):
                    if random.random() < density:
                        new_maze.h_walls[r][c] = True
                        
            # Generăm pereți interni verticali
            for r in range(rows):
                for c in range(1, cols):
                    if random.random() < density:
                        new_maze.v_walls[r][c] = True
            
            # Ne asigurăm că pozițiile de Start și Goal nu sunt blocate complet de pereți imediați
            sr, sc = new_maze.start
            gr, gc = new_maze.goal
            # Ștergem pereții din jurul punctului de start pentru siguranță
            new_maze.h_walls[sr][sc] = False
            new_maze.h_walls[sr+1][sc] = False
            new_maze.v_walls[sr][sc] = False
            new_maze.v_walls[sr][sc+1] = False
            
            self._maze = new_maze
            self.log(f"Generat labirint aleatoriu {rows}x{cols} (Densitate: {density:.2f}).")
            
        self._rows_var.set(str(rows))
        self._cols_var.set(str(cols))
        self._update_start_goal_entries()
        self._redraw()

    def _on_clear_walls(self) -> None:
        self._maze = GridMaze(self._maze.rows, self._maze.cols)
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
        if not name: return
        key = re.sub(r"\W+", "_", name.lower())
        self._presets[key] = (name, self._maze.clone())
        save_maze_presets(_CONFIG, {k: v[1] for k, v in self._presets.items()}, {k: v[0] for k, v in self._presets.items()})
        self._preset_cb.configure(values=[v[0] for v in self._presets.values()])
        self._preset_cb.set(name)

    def _apply_maze_to_ui(self, maze: GridMaze) -> None:
        self._maze = maze.clone()
        self._rows_var.set(str(self._maze.rows))
        self._cols_var.set(str(self._maze.cols))
        self._update_start_goal_entries()
        self._redraw()

    def _on_apply_maze(self) -> None:
        if not self.robot.connected: return
        try: cs = float(self._cell_m.get())
        except ValueError: cs = 0.5
        self._cell_size_m = cs
        try: setup_grid_maze(self.robot.sim, self._maze, cell_size=cs)
        except Exception: pass

    def _on_clear_scene(self) -> None:
        if self.robot.connected:
            try: clear_grid_maze(self.robot.sim)
            except Exception: pass

    def _on_connect(self) -> None:
        if self.robot.connected:
            self.robot.disconnect()
            self._conn_lbl.configure(text="● Deconectat", text_color="#ff3131")
            self._conn_btn.configure(text="Conectare", fg_color="#1f6aa5")
        else:
            host = self._host.get().strip() or "localhost"
            try: port = int(self._port.get().strip())
            except ValueError: port = 23000
            try:
                self.robot.connect(host, port)
                self._conn_lbl.configure(text="● Conectat", text_color="#55cc55")
                self._conn_btn.configure(text="Deconectare", fg_color="#7a2020")
            except Exception: pass

    def _rebuild_learning_params(self) -> None:
        for w in self._params_frame.winfo_children(): w.destroy()
        self._param_sliders.clear()
        for p in QLearningBehavior(self.robot).get_param_defs():
            row = ctk.CTkFrame(self._params_frame, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=p["label"], width=120, anchor="w").pack(side="left")
            vl = ctk.CTkLabel(row, text=f"{p['default']:.2f}", width=45)
            sl = ctk.CTkSlider(row, from_=p["min"], to=p["max"], command=lambda v, l=vl: l.configure(text=f"{v:.2f}"))
            sl.set(p["default"])
            sl.pack(side="left", fill="x", expand=True, padx=4)
            vl.pack(side="left")
            self._param_sliders[p["name"]] = sl

    def _on_start_beh(self) -> None:
        if not self.robot.connected: return
        try: self.robot.load_robot()
        except Exception: return
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
            gr, gc = self._maze.goal
            cell_sz = float(self._cell_m.get())
            goal_x = (gc * cell_sz) + (cell_sz / 2.0)
            goal_y = (gr * cell_sz) + (cell_sz / 2.0)
            while not self._stop_event.is_set():
                sensors = self.robot.read_sensors()
                vl, vr = beh.step(sensors)
                self.robot.set_velocity(vl, vr)
                pos = self.robot.get_position()
                if pos and len(pos) >= 2:
                    if math.hypot(pos[0] - goal_x, pos[1] - goal_y) < (cell_sz * 0.4):
                        if hasattr(beh, '_episode'): beh._episode += 1
                        self.robot.set_velocity(0.0, 0.0)
                        self.robot.stop_simulation()
                        time.sleep(0.1)
                        self.robot.start_simulation()
                        continue
                try: self._q.put_nowait({"type": "tick", "status": beh.get_status(), "vl": vl, "vr": vr, "sensors": sensors, "pos": pos})
                except queue.Full: pass
                time.sleep(DT)
        except Exception: pass
        finally:
            try:
                self.robot.set_velocity(0.0, 0.0)
                self.robot.stop_simulation()
            except Exception: pass
            try: self._q.put_nowait({"type": "stopped"})
            except queue.Full: pass

    def _on_run_compare(self) -> None:
        try: eps = int(self._exp_episodes.get())
        except Exception: eps = 50
        self._stop_event.clear()
        self._btn_bench.configure(state="disabled")
        threading.Thread(target=self._run_compare_worker, args=(eps,), daemon=True).start()

    def _run_compare_worker(self, episodes: int) -> None:
        import csv
        import matplotlib.pyplot as plt
        if not self.robot.connected:
            self._append_exp_output("Eroare: Conectează CoppeliaSim mai întâi!")
            self._btn_bench.configure(state="normal")
            return

        algoritmi = {0: "Q-learning", 1: "SARSA", 2: "Expected SARSA", 3: "Dyna-Q"}
        results = {id_alg: [] for id_alg in algoritmi.keys()}
        try:
            self.robot.load_robot()
            self.robot.start_simulation()
            for algo_id, algo_name in algoritmi.items():
                self._append_exp_output(f"\n[START] Rulează modelul: {algo_name}")
                beh = QLearningBehavior(self.robot)
                beh.algo = algo_id
                ep_done = 0
                last_episode = beh._episode
                current_ep_reward = 0.0
                while ep_done < episodes and not self._stop_event.is_set():
                    sensors = self.robot.read_sensors()
                    vl, vr = beh.step(sensors)
                    self.robot.set_velocity(vl, vr)
                    current_ep_reward += getattr(beh, '_last_reward', 0.0)
                    if beh._episode != last_episode:
                        results[algo_id].append(current_ep_reward)
                        ep_done += 1
                        last_episode = beh._episode
                        if ep_done % 10 == 0 or ep_done == episodes:
                            self._append_exp_output(f"  -> {algo_name} | Episod {ep_done}/{episodes} încheiat.")
                        current_ep_reward = 0.0
                    time.sleep(DT)
                if self._stop_event.is_set(): break

            # Salvare date grafic
            fig, ax = plt.subplots(figsize=(9, 5))
            for algo_id, algo_name in algoritmi.items():
                if results[algo_id]:
                    ax.plot(range(1, len(results[algo_id])+1), results[algo_id], label=algo_name, linewidth=2)
            ax.set_title("Studiu Comparativ Modele Reinforcement Learning"); ax.set_xlabel("Episoade"); ax.set_ylabel("Recompensă Cumulată")
            ax.grid(True); ax.legend()
            fig.savefig(_ROOT / "config" / "benchmark_last.png", bbox_inches="tight")
            plt.close(fig)
            self._append_exp_output("\n[SUCCES] Benchmark finalizat! Graficul s-a actualizat pe pagina principală.")
        except Exception as e:
            self._append_exp_output(f"Eroare proces: {e}")
        finally:
            try: self.robot.stop_simulation()
            except Exception: pass
            self._btn_bench.configure(state="normal")

    def _append_exp_output(self, text: str) -> None:
        try:
            self._exp_output.configure(state='normal')
            self._exp_output.insert('end', text + "\n")
            self._exp_output.see('end')
            self._exp_output.configure(state='disabled')
        except Exception: pass

    def _update_sensors(self, sensors: list[SensorReading], pos: tuple) -> None:
        for bar, lbl, s in zip(self._sbars, self._sdist, sensors):
            if s.detected:
                bar.set(max(0.0, min(1.0, 1.0 - s.distance)))
                lbl.configure(text=f"{s.distance:.2f}m")
            else:
                bar.set(0.0)
                lbl.configure(text="---")
        if pos and len(pos) >= 2:
            self._pos_lbl.configure(text=f"X={pos[0]:.2f} Y={pos[1]:.2f}")

    def _poll(self) -> None:
        try:
            while True:
                msg = self._q.get_nowait()
                if msg["type"] == "tick":
                    self._beh_status.configure(text=f"Status: {msg['status']}")
                    self._vel_lbl.configure(text=f"Viteze Motoare: vL = {msg['vl']:+.2f} | vR = {msg['vr']:+.2f}")
                    if self._auto_refresh.get():
                        self._update_sensors(msg["sensors"], msg["pos"])
                elif msg["type"] == "stopped":
                    self._start_btn.configure(state="normal")
                    self._stop_btn.configure(state="disabled")
        except queue.Empty: pass
        self.after(80, self._poll)

    def log(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"[{ts}] {msg}\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")


def _sep(parent: ctk.CTkFrame) -> None:
    ctk.CTkFrame(parent, height=1, fg_color="#1a103c").pack(fill="x", padx=12, pady=10)

def _draw_marker(canvas: tk.Canvas, cx: float, cy: float, r: float, color: str, label: str) -> None:
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="white", width=1)
    canvas.create_text(cx, cy, text=label, fill="white", font=("Arial", max(8, int(r * 1.1)), "bold"))

def _set_entry(e: ctk.CTkEntry, v: str) -> None:
    e.delete(0, "end")
    e.insert(0, v)
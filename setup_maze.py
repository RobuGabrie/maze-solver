"""
setup_maze.py – Generează un labirint procedural în CoppeliaSim
pentru robotul Pioneer P3-DX.

Scenariul este folosit ca mediu de antrenare pentru controllerul
Q-learning din GUI, iar labirintul rămâne compatibil și cu baseline-urile
clasice din proiect.

Algoritm: Recursive Backtracking (DFS randomizat) → labirint perfect
(exact un singur drum între oricare două celule).

Pași:
    1. Deschide CoppeliaSim
    2. Adaugă Pioneer P3-DX din Models Browser (NU porni simularea)
    3. python setup_maze.py [--rows 7] [--cols 7] [--seed 42]
    4. File → Save Scene As → maze.ttt
    5. Pornește simularea (▶) și conectează GUI-ul din `main.py`
"""
import argparse
import random
import math
import sys

from coppeliasim_zmqremoteapi_client import RemoteAPIClient

# ── parametri impliciți ────────────────────────────────────────────────────────
CELL_SIZE  = 0.80   # m – latura unei celule (>= 0.6 pentru Pioneer P3-DX)
WALL_T     = 0.12   # m – grosimea pereților
WALL_H     = 0.50   # m – înălțimea pereților

C_WALL     = [0.50, 0.50, 0.55]   # gri închis
C_EXIT     = [0.15, 0.75, 0.25]   # verde – marcare ieșire
C_START    = [0.20, 0.50, 0.85]   # albastru – marcare start


# ── generare labirint (DFS iterativ) ──────────────────────────────────────────

def generate_maze(rows: int, cols: int, seed=None):
    """
    DFS iterativ cu backtracking.

    Returnează:
        h_walls[row_idx][col_idx] – True dacă există perete orizontal
            row_idx = 0..rows  (0 = sud exterior, rows = nord exterior)
        v_walls[row_idx][col_idx] – True dacă există perete vertical
            col_idx = 0..cols  (0 = vest exterior, cols = est exterior)
    """
    rng = random.Random(seed)

    h_walls = [[True] * cols  for _ in range(rows + 1)]
    v_walls = [[True] * (cols + 1) for _ in range(rows)]
    visited = [[False] * cols for _ in range(rows)]

    stack = [(0, 0)]
    visited[0][0] = True

    while stack:
        r, c = stack[-1]
        neighbours = []
        for dr, dc, wall in [(1, 0, 'N'), (-1, 0, 'S'), (0, 1, 'E'), (0, -1, 'W')]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc]:
                neighbours.append((dr, dc, wall, nr, nc))

        if neighbours:
            _, _, wall, nr, nc = rng.choice(neighbours)
            if   wall == 'N': h_walls[r + 1][c]     = False
            elif wall == 'S': h_walls[r][c]          = False
            elif wall == 'E': v_walls[r][c + 1]      = False
            elif wall == 'W': v_walls[r][c]           = False
            visited[nr][nc] = True
            stack.append((nr, nc))
        else:
            stack.pop()

    # Ieșire: gaură în peretele nord al celulei din colțul dreapta-sus
    exit_row  = rows - 1
    exit_col  = cols - 1
    h_walls[rows][exit_col] = False   # nord exterior la coloana exit_col

    return h_walls, v_walls, exit_row, exit_col


# ── construcție în CoppeliaSim ────────────────────────────────────────────────

def make_cuboid(sim, size, pos, color, name: str) -> int:
    h = sim.createPrimitiveShape(sim.primitiveshape_cuboid, list(size), 0)
    sim.setObjectPosition(h, sim.handle_world, list(pos))
    sim.setShapeColor(h, None, sim.colorcomponent_ambient_diffuse, color)
    sim.setObjectInt32Param(h, sim.shapeintparam_static, 1)
    sim.setObjectAlias(h, name)
    return h


def build_walls(sim, rows: int, cols: int, h_walls, v_walls) -> int:
    total_w = cols * CELL_SIZE
    total_h = rows * CELL_SIZE
    ox = -total_w / 2   # coordonată X a marginii vestice
    oy = -total_h / 2   # coordonată Y a marginii sudice
    z  = WALL_H / 2
    n  = 0

    # Pereți orizontali (se întind pe axa X)
    for ri in range(rows + 1):
        for ci in range(cols):
            if not h_walls[ri][ci]:
                continue
            wx = ox + ci * CELL_SIZE + CELL_SIZE / 2
            wy = oy + ri * CELL_SIZE
            make_cuboid(sim, (CELL_SIZE, WALL_T, WALL_H), (wx, wy, z),
                        C_WALL, f"hw_{ri}_{ci}")
            n += 1

    # Pereți verticali (se întind pe axa Y)
    for ri in range(rows):
        for ci in range(cols + 1):
            if not v_walls[ri][ci]:
                continue
            wx = ox + ci * CELL_SIZE
            wy = oy + ri * CELL_SIZE + CELL_SIZE / 2
            make_cuboid(sim, (WALL_T, CELL_SIZE, WALL_H), (wx, wy, z),
                        C_WALL, f"vw_{ri}_{ci}")
            n += 1

    return n


def add_marker(sim, rows: int, cols: int, exit_row: int, exit_col: int) -> None:
    """Adaugă markere plate: albastru la start, verde la ieșire."""
    total_w = cols * CELL_SIZE
    total_h = rows * CELL_SIZE
    ox, oy = -total_w / 2, -total_h / 2
    marker_h = 0.02

    # Start – colțul stânga-jos, celula (0, 0)
    sx = ox + CELL_SIZE / 2
    sy = oy + CELL_SIZE / 2
    make_cuboid(sim, (CELL_SIZE * 0.7, CELL_SIZE * 0.7, marker_h),
                (sx, sy, marker_h / 2), C_START, "marker_start")

    # Ieșire – chiar în afara labirintului, deasupra celulei exit
    ex = ox + exit_col * CELL_SIZE + CELL_SIZE / 2
    ey = oy + total_h + CELL_SIZE * 0.3
    make_cuboid(sim, (CELL_SIZE * 0.9, CELL_SIZE * 0.5, marker_h),
                (ex, ey, marker_h / 2), C_EXIT, "marker_exit")
    print(f"  Marker start  ({sx:.2f}, {sy:.2f})")
    print(f"  Marker ieșire ({ex:.2f}, {ey:.2f})  ← ținta robotului")


ROBOT_HEIGHT = 0.1385   # m – înălțimea centrului Pioneer P3-DX față de podea

# Căi relative față de directorul de instalare CoppeliaSim
_MODEL_CANDIDATES = [
    "models/robots/mobile/PioneerP3DX.ttm",
    "models/robots/mobile/Pioneer p3-dx.ttm",
    "models/robots/mobile/pioneer p3-dx.ttm",
]


def _find_model(app_path: str) -> str | None:
    import os
    for rel in _MODEL_CANDIDATES:
        full = os.path.join(app_path, rel)
        if os.path.isfile(full):
            return full
    return None


def place_robot(sim, rows: int, cols: int) -> None:
    total_w = cols * CELL_SIZE
    total_h = rows * CELL_SIZE
    sx = -total_w / 2 + CELL_SIZE / 2
    sy = -total_h / 2 + CELL_SIZE / 2

    # Verifică dacă robotul există deja în scenă
    try:
        robot = sim.getObject('/PioneerP3DX')
        sim.setObjectPosition(robot, sim.handle_world, [sx, sy, ROBOT_HEIGHT])
        print(f"  Robot găsit în scenă – mutat la ({sx:.2f}, {sy:.2f})")
        return
    except Exception:
        pass

    # Încearcă să îl încarce automat din directorul CoppeliaSim
    app_path = sim.getStringParam(sim.stringparam_application_path)
    model_path = _find_model(app_path)

    if model_path:
        robot = sim.loadModel(model_path)
        sim.setObjectPosition(robot, sim.handle_world, [sx, sy, ROBOT_HEIGHT])
        print(f"  Robot încărcat din: {model_path}")
        print(f"  Plasat la ({sx:.2f}, {sy:.2f})")
    else:
        print(f"  Model negăsit automat în: {app_path}")
        print(f"  Adaugă robotul manual din Models Browser")
        print(f"  și mută-l la ({sx:.2f}, {sy:.2f}, {ROBOT_HEIGHT})")


# ── vizualizare ASCII ─────────────────────────────────────────────────────────

def print_ascii(rows: int, cols: int, h_walls, v_walls,
                exit_row: int, exit_col: int) -> None:
    print()
    for r in range(rows - 1, -1, -1):
        # Linia cu peretele de deasupra rândului r
        top = ""
        for c in range(cols):
            top += "+" + ("───" if h_walls[r + 1][c] else "   ")
        top += "+"
        print(" ", top)

        # Linia cu celulele rândului r
        mid = ""
        for c in range(cols):
            mid += ("│" if v_walls[r][c] else " ")
            if r == 0 and c == 0:
                mid += " S "
            elif r == exit_row and c == exit_col:
                mid += " E "
            else:
                mid += "   "
        mid += ("│" if v_walls[r][cols] else " ")
        print(" ", mid)

    # Peretele de jos
    bot = ""
    for c in range(cols):
        bot += "+" + ("───" if h_walls[0][c] else "   ")
    bot += "+"
    print(" ", bot)
    print()
    print("  S = start robot   E = ieșire labirint")


# ── salvare PNG ───────────────────────────────────────────────────────────────

def save_png(rows: int, cols: int, h_walls, v_walls,
             exit_row: int, exit_col: int, path: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except ImportError:
        print("  (matplotlib lipsă – PNG nesalvat)")
        return

    fig_w = cols * CELL_SIZE * 2
    fig_h = rows * CELL_SIZE * 2
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, cols)
    ax.set_ylim(0, rows)
    ax.set_aspect("equal")
    ax.axis("off")

    # Fundal
    ax.add_patch(Rectangle((0, 0), cols, rows, color="#f5f5f5"))

    # Celulă start
    ax.add_patch(Rectangle((0, 0), 1, 1, color="#cce5ff", zorder=1))
    ax.text(0.5, 0.5, "S", ha="center", va="center", fontsize=14, fontweight="bold", color="#1a56c4")

    # Celulă ieșire
    ax.add_patch(Rectangle((exit_col, exit_row), 1, 1, color="#d4edda", zorder=1))
    ax.text(exit_col + 0.5, exit_row + 0.5, "E", ha="center", va="center",
            fontsize=14, fontweight="bold", color="#155724")

    wall_color = "#333344"
    lw = 3.5

    # Pereți orizontali
    for ri in range(rows + 1):
        for ci in range(cols):
            if h_walls[ri][ci]:
                ax.plot([ci, ci + 1], [ri, ri], color=wall_color, lw=lw, solid_capstyle="round")

    # Pereți verticali
    for ri in range(rows):
        for ci in range(cols + 1):
            if v_walls[ri][ci]:
                ax.plot([ci, ci], [ri, ri + 1], color=wall_color, lw=lw, solid_capstyle="round")

    plt.title(f"Labirint {rows}×{cols}  (S = start, E = ieșire)", fontsize=13, pad=10)
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  PNG salvat: {path}")


# ── entry point ───────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Generează labirint procedural în CoppeliaSim")
    p.add_argument("--rows", type=int, default=7,
                   help="Număr de rânduri de celule (default: 7)")
    p.add_argument("--cols", type=int, default=7,
                   help="Număr de coloane de celule (default: 7)")
    p.add_argument("--seed", type=int, default=None,
                   help="Seed aleatoriu pentru reproductibilitate (default: aleator)")
    p.add_argument("--port", type=int, default=23000,
                   help="Port ZMQ CoppeliaSim (default: 23000)")
    return p.parse_args()


def main():
    args = parse_args()

    print(f"Conectare la CoppeliaSim (port {args.port})…")
    client = RemoteAPIClient(port=args.port)
    sim    = client.require("sim")
    print("Conectat.\n")

    rows, cols = args.rows, args.cols
    total_w = cols * CELL_SIZE
    total_h = rows * CELL_SIZE
    corridor = CELL_SIZE - WALL_T

    print(f"Parametri labirint:")
    print(f"  Dimensiune grid  : {rows} × {cols} celule")
    print(f"  Dimensiune arenă : {total_w:.1f} × {total_h:.1f} m")
    print(f"  Lățime coridor   : {corridor:.2f} m  (Pioneer P3-DX = ~0.45 m)")
    print(f"  Seed             : {args.seed if args.seed is not None else 'aleator'}")
    print()

    if corridor < 0.50:
        print("AVERTISMENT: coridor < 0.5 m, robotul poate nu încape.")
        print("  Mărește CELL_SIZE în fișier sau micșorează --rows/--cols.\n")

    print("Generare labirint…")
    h_walls, v_walls, exit_row, exit_col = generate_maze(rows, cols, args.seed)

    print("Construcție pereți în scenă…")
    n_walls = build_walls(sim, rows, cols, h_walls, v_walls)
    print(f"  {n_walls} segmente de perete create.")

    print("\nAdăugare markere…")
    add_marker(sim, rows, cols, exit_row, exit_col)

    print("\nPozitionare robot…")
    place_robot(sim, rows, cols)

    # Exit world coordinates (used by maze_explorer.py)
    ex_x = -total_w / 2 + exit_col * CELL_SIZE + CELL_SIZE / 2
    ex_y =  total_h / 2
    print(f"\nCoordonate ieșire (pentru --exit): {ex_x:.3f} {ex_y:.3f}")

    print("\nHarta labirintului:")
    print_ascii(rows, cols, h_walls, v_walls, exit_row, exit_col)

    print("Salvare PNG…")
    save_png(rows, cols, h_walls, v_walls, exit_row, exit_col, "maze_layout.png")

    scene_path = sim.getStringParam(sim.stringparam_scene_path_and_name)
    if scene_path:
        sim.saveScene(scene_path)
        print(f"\nScena salvată: {scene_path}")
    else:
        print("\nATENȚIE: scena nu are încă un nume.")
        print("  Salvează manual: File → Save Scene As → maze.ttt")

    print("\n═══════════════════════════════════════════════════")
    print("  Gata! Acum:")
    print("  1. Salvează scena (File → Save Scene As → maze.ttt)")
    print("  2. Pornește simularea (▶)")
    print(f"  3. python maze_explorer.py --algorithm tremaux --save-map")
    print("═══════════════════════════════════════════════════")


if __name__ == "__main__":
    main()

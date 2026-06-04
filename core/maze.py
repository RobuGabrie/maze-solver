"""
core/maze.py - Grid-based maze representation, generation, and CoppeliaSim builder.

Coordinate convention (rows × cols grid):
  - Row 0 is the TOP of the maze (north)
  - Col 0 is the LEFT of the maze (west)

Wall arrays:
  h_walls[r][c]  — horizontal wall ABOVE cell (r, c)  (r in 0..rows, c in 0..cols-1)
  v_walls[r][c]  — vertical wall LEFT of cell (r, c)   (r in 0..rows-1, c in 0..cols)

Boundary walls (r=0, r=rows for h; c=0, c=cols for v) are always True and not togglable.
"""
import json
import os
import random
from pathlib import Path

WALL_COLOR   = [0.55, 0.55, 0.60]
WALL_HEX     = "#7a7a8a"
BOUNDARY_HEX = "#4466aa"


# ══════════════════════════════════════════════════════════════════════
# GridMaze
# ══════════════════════════════════════════════════════════════════════

class GridMaze:
    def __init__(self, rows: int, cols: int) -> None:
        self.rows = rows
        self.cols = cols
        # h_walls: (rows+1) × cols  — boundary rows are always True
        self.h_walls: list[list[bool]] = [
            [r == 0 or r == rows for _ in range(cols)]
            for r in range(rows + 1)
        ]
        # v_walls: rows × (cols+1)  — boundary cols are always True
        self.v_walls: list[list[bool]] = [
            [c == 0 or c == cols for c in range(cols + 1)]
            for _ in range(rows)
        ]
        self.start: tuple[int, int] = (0, 0)
        self.goal: tuple[int, int] = (rows - 1, cols - 1)

    # ── wall accessors ────────────────────────────────────────────

    def wall_n(self, r: int, c: int) -> bool:
        return self.h_walls[r][c]

    def wall_s(self, r: int, c: int) -> bool:
        return self.h_walls[r + 1][c]

    def wall_w(self, r: int, c: int) -> bool:
        return self.v_walls[r][c]

    def wall_e(self, r: int, c: int) -> bool:
        return self.v_walls[r][c + 1]

    def can_go(self, r: int, c: int, dr: int, dc: int) -> bool:
        nr, nc = r + dr, c + dc
        if not (0 <= nr < self.rows and 0 <= nc < self.cols):
            return False
        if dr == -1: return not self.wall_n(r, c)
        if dr == +1: return not self.wall_s(r, c)
        if dc == -1: return not self.wall_w(r, c)
        if dc == +1: return not self.wall_e(r, c)
        return False

    def neighbors(self, r: int, c: int) -> list[tuple[int, int]]:
        return [
            (r + dr, c + dc)
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
            if self.can_go(r, c, dr, dc)
        ]

    # ── wall editing ──────────────────────────────────────────────

    def toggle_h_wall(self, r: int, c: int) -> None:
        """Toggle interior horizontal wall. Silently ignores boundary."""
        if 0 < r < self.rows and 0 <= c < self.cols:
            self.h_walls[r][c] = not self.h_walls[r][c]

    def toggle_v_wall(self, r: int, c: int) -> None:
        """Toggle interior vertical wall. Silently ignores boundary."""
        if 0 <= r < self.rows and 0 < c < self.cols:
            self.v_walls[r][c] = not self.v_walls[r][c]

    def set_h_wall(self, r: int, c: int, val: bool) -> None:
        if 0 < r < self.rows and 0 <= c < self.cols:
            self.h_walls[r][c] = val

    def set_v_wall(self, r: int, c: int, val: bool) -> None:
        if 0 <= r < self.rows and 0 < c < self.cols:
            self.v_walls[r][c] = val

    def is_boundary_h(self, r: int) -> bool:
        return r == 0 or r == self.rows

    def is_boundary_v(self, c: int) -> bool:
        return c == 0 or c == self.cols

    # ── serialization ─────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "rows": self.rows,
            "cols": self.cols,
            "h_walls": self.h_walls,
            "v_walls": self.v_walls,
            "start": list(self.start),
            "goal": list(self.goal),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GridMaze":
        m = cls(d["rows"], d["cols"])
        m.h_walls = [list(row) for row in d["h_walls"]]
        m.v_walls = [list(row) for row in d["v_walls"]]
        m.start = tuple(d["start"])
        m.goal  = tuple(d["goal"])
        return m

    def clone(self) -> "GridMaze":
        return GridMaze.from_dict(self.to_dict())

    # ── coordinate helpers ────────────────────────────────────────

    def cell_world_pos(self, r: int, c: int, cell_size: float) -> tuple[float, float]:
        """Center of cell (r,c) in CoppeliaSim world coordinates (meters)."""
        maze_w = self.cols * cell_size
        maze_h = self.rows * cell_size
        x = -maze_w / 2 + (c + 0.5) * cell_size
        y =  maze_h / 2 - (r + 0.5) * cell_size
        return x, y


# ══════════════════════════════════════════════════════════════════════
# Maze generation (recursive backtracking — perfect maze)
# ══════════════════════════════════════════════════════════════════════

def generate_maze(rows: int, cols: int, seed: int | None = None) -> GridMaze:
    """Generate a perfect maze (exactly one path between any two cells)."""
    rng = random.Random(seed)
    maze = GridMaze(rows, cols)

    # Fill all interior walls
    for r in range(1, rows):
        for c in range(cols):
            maze.h_walls[r][c] = True
    for r in range(rows):
        for c in range(1, cols):
            maze.v_walls[r][c] = True

    visited = [[False] * cols for _ in range(rows)]
    dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    stack = [(0, 0)]
    visited[0][0] = True

    while stack:
        r, c = stack[-1]
        rng.shuffle(dirs)
        moved = False
        for dr, dc in dirs:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc]:
                # Remove wall between (r,c) and (nr,nc)
                if dr == -1: maze.h_walls[r][c]     = False
                elif dr == 1: maze.h_walls[r + 1][c] = False
                elif dc == -1: maze.v_walls[r][c]    = False
                elif dc == 1: maze.v_walls[r][c + 1] = False
                visited[nr][nc] = True
                stack.append((nr, nc))
                moved = True
                break
        if not moved:
            stack.pop()

    return maze


# ══════════════════════════════════════════════════════════════════════
# CoppeliaSim scene builder
# ══════════════════════════════════════════════════════════════════════

def _make_cuboid(sim, size, pos, color, name) -> int:
    handle = sim.createPrimitiveShape(sim.primitiveshape_cuboid, list(size), 0)
    sim.setObjectPosition(handle, sim.handle_world, list(pos))
    sim.setShapeColor(handle, None, sim.colorcomponent_ambient_diffuse, color)
    sim.setObjectInt32Param(handle, sim.shapeintparam_static, 1)
    sim.setObjectAlias(handle, name)
    return handle


def _remove_if_exists(sim, name: str) -> bool:
    try:
        h = sim.getObject(f"/{name}")
        sim.removeObject(h)
        return True
    except Exception:
        return False


def clear_grid_maze(sim) -> int:
    """Remove all maze objects (walls + plates) from the scene."""
    removed = 0
    for i in range(1000):
        name = f"mhw_{i}" if i < 500 else f"mvw_{i - 500}"
        if _remove_if_exists(sim, name):
            removed += 1
    for name in ("maze_start_plate", "maze_goal_plate", "maze_floor"):
        if _remove_if_exists(sim, name):
            removed += 1
    return removed


def setup_grid_maze(
    sim,
    maze: GridMaze,
    cell_size: float = 0.5,
    wall_thickness: float = 0.1,
    wall_height: float = 0.5,
) -> list[str]:
    """Build the maze in CoppeliaSim. Merges adjacent wall segments into single cuboids."""
    log: list[str] = []
    clear_grid_maze(sim)

    rows, cols = maze.rows, maze.cols
    maze_w = cols * cell_size
    maze_h = rows * cell_size
    wt, wh = wall_thickness, wall_height
    hw_idx = vw_idx = 0

    # ── horizontal walls (merge consecutive True cells in same row) ──
    for r in range(rows + 1):
        c = 0
        while c < cols:
            if maze.h_walls[r][c]:
                start_c = c
                while c < cols and maze.h_walls[r][c]:
                    c += 1
                # span: cols start_c..c-1
                length = (c - start_c) * cell_size + wt
                cx = -maze_w / 2 + (start_c + c) / 2 * cell_size
                cy =  maze_h / 2 - r * cell_size
                name = f"mhw_{hw_idx}"
                h = _make_cuboid(sim, (length, wt, wh), (cx, cy, wh / 2), WALL_COLOR, name)
                log.append(f"H-wall row={r} cols={start_c}..{c-1} -> {h}")
                hw_idx += 1
            else:
                c += 1

    # ── vertical walls (merge consecutive True cells in same column) ──
    for c in range(cols + 1):
        r = 0
        while r < rows:
            if maze.v_walls[r][c]:
                start_r = r
                while r < rows and maze.v_walls[r][c]:
                    r += 1
                length = (r - start_r) * cell_size + wt
                cx = -maze_w / 2 + c * cell_size
                cy =  maze_h / 2 - (start_r + r) / 2 * cell_size
                name = f"mvw_{vw_idx}"
                h = _make_cuboid(sim, (wt, length, wh), (cx, cy, wh / 2), WALL_COLOR, name)
                log.append(f"V-wall col={c} rows={start_r}..{r-1} -> {h}")
                vw_idx += 1
            else:
                r += 1

    # ── resize existing scene floor ───────────────────────────────
    floor_w = cols * cell_size + wt * 2
    floor_h = rows * cell_size + wt * 2
    log.append(_resize_floor(sim, floor_w, floor_h))

    # ── floor plates ──────────────────────────────────────────────
    sx, sy = maze.cell_world_pos(*maze.start, cell_size)
    gx, gy = maze.cell_world_pos(*maze.goal,  cell_size)
    plate_side = cell_size * 0.88

    h = _make_plate(sim, sx, sy, plate_side, [0.15, 0.80, 0.25], "maze_start_plate")
    log.append(f"Start plate (green) -> cell {maze.start} = ({sx:.2f}, {sy:.2f})  handle={h}")

    h = _make_plate(sim, gx, gy, plate_side, [0.85, 0.15, 0.15], "maze_goal_plate")
    log.append(f"Goal  plate (red)   -> cell {maze.goal}  = ({gx:.2f}, {gy:.2f})  handle={h}")

    # ── spawn / reposition robot ──────────────────────────────────
    msg = _spawn_robot(sim, sx, sy)
    log.append(msg)

    log.append(f"Maze built: {hw_idx} h-walls, {vw_idx} v-walls")
    return log


def _resize_floor(sim, target_w: float, target_h: float) -> str:
    """Replace the scene floor with a correctly-sized static cuboid."""
    # Remove the original ResizableFloor and any previously created maze_floor.
    # getShapeBB fails on CoppeliaSim's ResizableFloor (not a regular shape),
    # so we recreate rather than scale.
    for name in ("Floor", "maze_floor"):
        _remove_if_exists(sim, name)

    try:
        handle = sim.createPrimitiveShape(sim.primitiveshape_cuboid, [target_w, target_h, 0.02], 0)
        sim.setObjectPosition(handle, sim.handle_world, [0.0, 0.0, -0.01])
        sim.setShapeColor(handle, None, sim.colorcomponent_ambient_diffuse, [0.55, 0.55, 0.55])
        sim.setObjectInt32Param(handle, sim.shapeintparam_static, 1)
        sim.setObjectInt32Param(handle, sim.shapeintparam_respondable, 1)
        sim.setObjectAlias(handle, "maze_floor")
    except Exception as exc:
        return f"Could not create floor: {exc}"

    return f"Floor created: {target_w:.2f} × {target_h:.2f} m"


def _make_plate(sim, x: float, y: float, side: float,
                color: list[float], name: str) -> int:
    """Thin flat plate (z=0.01 m) placed on the floor."""
    handle = sim.createPrimitiveShape(sim.primitiveshape_cuboid, [side, side, 0.02], 0)
    sim.setObjectPosition(handle, sim.handle_world, [x, y, 0.01])
    sim.setShapeColor(handle, None, sim.colorcomponent_ambient_diffuse, color)
    sim.setObjectInt32Param(handle, sim.shapeintparam_static, 1)
    sim.setObjectAlias(handle, name)
    return handle


def _spawn_robot(sim, x: float, y: float) -> str:
    """Reposition existing Pioneer P3-DX or load the model from the CoppeliaSim library."""
    # 1. Already in scene — just move it
    try:
        robot = sim.getObject("/PioneerP3DX")
        pos = sim.getObjectPosition(robot, sim.handle_world)
        sim.setObjectPosition(robot, sim.handle_world, [x, y, pos[2]])
        return f"Robot repositioned -> ({x:.2f}, {y:.2f})"
    except Exception:
        pass

    # 2. Try to load from the standard CoppeliaSim models directory
    try:
        app_dir = sim.getStringParam(sim.stringparam_applicationdir)
        candidates = [
            os.path.join(app_dir, "models", "robots", "mobile", "pioneer p3-dx.ttm"),
            os.path.join(app_dir, "models", "robots", "mobile", "Pioneer p3-dx.ttm"),
        ]
        for path in candidates:
            if os.path.exists(path):
                handle = sim.loadModel(path)
                pos = sim.getObjectPosition(handle, sim.handle_world)
                sim.setObjectPosition(handle, sim.handle_world, [x, y, pos[2]])
                return f"Robot loaded from model library -> ({x:.2f}, {y:.2f})"
        return "Robot model not found — add Pioneer P3-DX manually from Models Browser."
    except Exception as e:
        return f"Could not spawn robot: {e}"


# ══════════════════════════════════════════════════════════════════════
# Preset persistence
# ══════════════════════════════════════════════════════════════════════

def load_maze_presets(path: Path) -> dict[str, GridMaze]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {key: GridMaze.from_dict(v) for key, v in data.get("presets", {}).items()}


def save_maze_presets(path: Path, presets: dict[str, GridMaze], names: dict[str, str]) -> None:
    data: dict = {"presets": {}}
    for key, maze in presets.items():
        d = maze.to_dict()
        d["display_name"] = names.get(key, key)
        data["presets"][key] = d
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_maze_presets_with_names(path: Path) -> dict[str, tuple[str, GridMaze]]:
    """Returns {key: (display_name, GridMaze)}."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    result = {}
    for key, v in data.get("presets", {}).items():
        name = v.get("display_name", key)
        result[key] = (name, GridMaze.from_dict(v))
    return result

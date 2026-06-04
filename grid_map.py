"""Occupancy grid map with visit tracking and BFS path finding."""
import numpy as np
from collections import deque
from enum import IntEnum


class Cell(IntEnum):
    UNKNOWN = 0
    FREE = 1
    WALL = 2


class GridMap:
    CELL_SIZE = 0.25  # metres per cell

    def __init__(self, size: int = 200):
        self._size = size
        self._offset = size // 2
        self._grid = np.full((size, size), Cell.UNKNOWN, dtype=np.int8)
        self._visits = np.zeros((size, size), dtype=np.int16)

    # ── coordinate helpers ────────────────────────────────────────────────

    def to_grid(self, x: float, y: float) -> tuple[int, int]:
        return (
            int(x / self.CELL_SIZE) + self._offset,
            int(y / self.CELL_SIZE) + self._offset,
        )

    def to_world(self, gx: int, gy: int) -> tuple[float, float]:
        return (
            (gx - self._offset) * self.CELL_SIZE,
            (gy - self._offset) * self.CELL_SIZE,
        )

    def _ok(self, gx: int, gy: int) -> bool:
        return 0 <= gx < self._size and 0 <= gy < self._size

    # ── map updates ───────────────────────────────────────────────────────

    def mark_free(self, x: float, y: float) -> None:
        gx, gy = self.to_grid(x, y)
        if self._ok(gx, gy) and self._grid[gy, gx] != Cell.WALL:
            self._grid[gy, gx] = Cell.FREE

    def mark_wall(self, x: float, y: float) -> None:
        gx, gy = self.to_grid(x, y)
        if self._ok(gx, gy):
            self._grid[gy, gx] = Cell.WALL

    def mark_ray(self, sx: float, sy: float, wx: float, wy: float) -> None:
        """Bresenham ray: mark cells free up to wall endpoint."""
        x0, y0 = self.to_grid(sx, sy)
        x1, y1 = self.to_grid(wx, wy)
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx_s = 1 if x0 < x1 else -1
        sy_s = 1 if y0 < y1 else -1
        err = dx - dy
        cx, cy = x0, y0
        while True:
            if cx == x1 and cy == y1:
                if self._ok(cx, cy):
                    self._grid[cy, cx] = Cell.WALL
                break
            if not self._ok(cx, cy):
                break
            if self._grid[cy, cx] != Cell.WALL:
                self._grid[cy, cx] = Cell.FREE
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                cx += sx_s
            if e2 < dx:
                err += dx
                cy += sy_s

    # ── visit tracking ────────────────────────────────────────────────────

    def visit(self, x: float, y: float) -> int:
        """Increment visit count and return new count."""
        gx, gy = self.to_grid(x, y)
        if self._ok(gx, gy):
            self._visits[gy, gx] += 1
            return int(self._visits[gy, gx])
        return 0

    def get_visits(self, x: float, y: float) -> int:
        gx, gy = self.to_grid(x, y)
        if self._ok(gx, gy):
            return int(self._visits[gy, gx])
        return 99

    def is_wall(self, x: float, y: float) -> bool:
        gx, gy = self.to_grid(x, y)
        if not self._ok(gx, gy):
            return True
        return bool(self._grid[gy, gx] == Cell.WALL)

    # ── path finding ──────────────────────────────────────────────────────

    def bfs_path(
        self,
        start_x: float,
        start_y: float,
        goal_x: float,
        goal_y: float,
    ) -> list[tuple[float, float]] | None:
        """BFS shortest path in world coordinates, or None if unreachable."""
        start = self.to_grid(start_x, start_y)
        goal = self.to_grid(goal_x, goal_y)
        if not self._ok(*start) or not self._ok(*goal):
            return None
        queue: deque = deque([(start, [start])])
        seen = {start}
        while queue:
            (cx, cy), path = queue.popleft()
            if (cx, cy) == goal:
                return [self.to_world(gx, gy) for gx, gy in path]
            for nx, ny in [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]:
                if (nx, ny) not in seen and self._ok(nx, ny):
                    if self._grid[ny, nx] != Cell.WALL:
                        seen.add((nx, ny))
                        queue.append(((nx, ny), path + [(nx, ny)]))
        return None

    # ── visualisation ─────────────────────────────────────────────────────

    def save_png(self, path: str, trajectory: list[tuple[float, float]] | None = None) -> None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        img = np.zeros((*self._grid.shape, 3), dtype=np.uint8)
        img[self._grid == Cell.UNKNOWN] = [180, 180, 180]
        img[self._grid == Cell.FREE] = [255, 255, 255]
        img[self._grid == Cell.WALL] = [30, 30, 30]

        visited_mask = (self._visits > 0) & (self._grid == Cell.FREE)
        img[visited_mask] = [200, 230, 255]

        fig, ax = plt.subplots(figsize=(10, 10))
        ax.imshow(img, origin="lower")

        if trajectory:
            gxs = [self.to_grid(x, y)[0] for x, y in trajectory]
            gys = [self.to_grid(x, y)[1] for x, y in trajectory]
            ax.plot(gxs, gys, "b-", linewidth=1, alpha=0.7, label="Trajectory")
            ax.plot(gxs[0], gys[0], "go", markersize=8, label="Start")
            ax.plot(gxs[-1], gys[-1], "rs", markersize=8, label="End")
            ax.legend()

        ax.set_title("Occupancy Grid Map")
        ax.set_xlabel("Grid X")
        ax.set_ylabel("Grid Y")
        plt.tight_layout()
        plt.savefig(path, dpi=150)
        plt.close()

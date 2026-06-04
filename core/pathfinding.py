"""
core/pathfinding.py - Pathfinding algorithms for GridMaze.

Each algorithm returns a PathResult with:
  path       — ordered list of (row, col) from start to goal (None if unsolvable)
  explored   — cells visited in order (for step-by-step animation)
  algorithm  — name string
  time_ms    — wall-clock time taken
"""
import heapq
import time
from collections import deque
from dataclasses import dataclass, field

from .maze import GridMaze


# ══════════════════════════════════════════════════════════════════════
# Result type
# ══════════════════════════════════════════════════════════════════════

@dataclass
class PathResult:
    algorithm: str
    path: list[tuple[int, int]] | None
    explored: list[tuple[int, int]]
    time_ms: float

    @property
    def found(self) -> bool:
        return self.path is not None

    @property
    def path_length(self) -> int:
        """Number of steps (edges) in the path."""
        return len(self.path) - 1 if self.path else 0

    @property
    def explored_count(self) -> int:
        return len(self.explored)


# ══════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════

def _reconstruct(came_from: dict, start: tuple, goal: tuple) -> list[tuple[int, int]]:
    path = []
    node = goal
    while node is not None:
        path.append(node)
        node = came_from[node]
    path.reverse()
    return path


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ══════════════════════════════════════════════════════════════════════
# Algorithms
# ══════════════════════════════════════════════════════════════════════

def bfs(maze: GridMaze) -> PathResult:
    """Breadth-First Search — guaranteed shortest path (unweighted)."""
    start, goal = maze.start, maze.goal
    t0 = time.perf_counter()

    queue: deque = deque([start])
    came_from: dict = {start: None}
    explored: list = []

    while queue:
        cur = queue.popleft()
        explored.append(cur)
        if cur == goal:
            return PathResult("BFS", _reconstruct(came_from, start, goal),
                              explored, (time.perf_counter() - t0) * 1000)
        for nb in maze.neighbors(*cur):
            if nb not in came_from:
                came_from[nb] = cur
                queue.append(nb)

    return PathResult("BFS", None, explored, (time.perf_counter() - t0) * 1000)


def dfs(maze: GridMaze) -> PathResult:
    """Depth-First Search — finds A path, not necessarily shortest."""
    start, goal = maze.start, maze.goal
    t0 = time.perf_counter()

    stack = [start]
    came_from: dict = {start: None}
    explored: list = []

    while stack:
        cur = stack.pop()
        if cur in explored:
            continue
        explored.append(cur)
        if cur == goal:
            return PathResult("DFS", _reconstruct(came_from, start, goal),
                              explored, (time.perf_counter() - t0) * 1000)
        for nb in maze.neighbors(*cur):
            if nb not in came_from:
                came_from[nb] = cur
                stack.append(nb)

    return PathResult("DFS", None, explored, (time.perf_counter() - t0) * 1000)


def dijkstra(maze: GridMaze) -> PathResult:
    """Dijkstra's algorithm — shortest path with uniform cost (same as BFS here)."""
    start, goal = maze.start, maze.goal
    t0 = time.perf_counter()

    heap = [(0, start)]
    came_from: dict = {start: None}
    g_cost: dict = {start: 0}
    explored: list = []
    in_explored: set = set()

    while heap:
        cost, cur = heapq.heappop(heap)
        if cur in in_explored:
            continue
        in_explored.add(cur)
        explored.append(cur)
        if cur == goal:
            return PathResult("Dijkstra", _reconstruct(came_from, start, goal),
                              explored, (time.perf_counter() - t0) * 1000)
        for nb in maze.neighbors(*cur):
            new_cost = g_cost[cur] + 1
            if nb not in g_cost or new_cost < g_cost[nb]:
                g_cost[nb] = new_cost
                came_from[nb] = cur
                heapq.heappush(heap, (new_cost, nb))

    return PathResult("Dijkstra", None, explored, (time.perf_counter() - t0) * 1000)


def astar(maze: GridMaze) -> PathResult:
    """A* with Manhattan distance heuristic — optimal and focused."""
    start, goal = maze.start, maze.goal
    t0 = time.perf_counter()

    heap = [(_manhattan(start, goal), 0, start)]
    came_from: dict = {start: None}
    g_cost: dict = {start: 0}
    explored: list = []
    in_explored: set = set()

    while heap:
        _, g, cur = heapq.heappop(heap)
        if cur in in_explored:
            continue
        in_explored.add(cur)
        explored.append(cur)
        if cur == goal:
            return PathResult("A*", _reconstruct(came_from, start, goal),
                              explored, (time.perf_counter() - t0) * 1000)
        for nb in maze.neighbors(*cur):
            new_g = g_cost[cur] + 1
            if nb not in g_cost or new_g < g_cost[nb]:
                g_cost[nb] = new_g
                came_from[nb] = cur
                heapq.heappush(heap, (new_g + _manhattan(nb, goal), new_g, nb))

    return PathResult("A*", None, explored, (time.perf_counter() - t0) * 1000)


def greedy_bfs(maze: GridMaze) -> PathResult:
    """Greedy Best-First — fast, heuristic-only, not guaranteed optimal."""
    start, goal = maze.start, maze.goal
    t0 = time.perf_counter()

    heap = [(_manhattan(start, goal), start)]
    came_from: dict = {start: None}
    explored: list = []
    in_explored: set = set()

    while heap:
        _, cur = heapq.heappop(heap)
        if cur in in_explored:
            continue
        in_explored.add(cur)
        explored.append(cur)
        if cur == goal:
            return PathResult("Greedy BFS", _reconstruct(came_from, start, goal),
                              explored, (time.perf_counter() - t0) * 1000)
        for nb in maze.neighbors(*cur):
            if nb not in came_from:
                came_from[nb] = cur
                heapq.heappush(heap, (_manhattan(nb, goal), nb))

    return PathResult("Greedy BFS", None, explored, (time.perf_counter() - t0) * 1000)


# ══════════════════════════════════════════════════════════════════════
# Registry
# ══════════════════════════════════════════════════════════════════════

ALGORITHMS: dict[str, callable] = {
    "BFS (shortest)":  bfs,
    "DFS":             dfs,
    "Dijkstra":        dijkstra,
    "A* (Manhattan)":  astar,
    "Greedy BFS":      greedy_bfs,
}

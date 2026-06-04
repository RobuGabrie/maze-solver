"""
core/grid_rl.py - Self-contained RL benchmark on GridMaze.
No CoppeliaSim required. Each algorithm runs N episodes
and returns per-episode (total_reward, steps, reached_goal).
"""
import random
from .maze import GridMaze

# N, E, S, W
_MOVES = [(-1, 0), (0, 1), (1, 0), (0, -1)]
N_ACTIONS = 4


class GridEnv:
    """Simulates a robot walking a GridMaze cell by cell."""

    def __init__(self, maze: GridMaze):
        self.maze = maze
        self.max_steps = maze.rows * maze.cols * 6
        self._pos = maze.start
        self._steps = 0

    def reset(self) -> tuple[int, int]:
        self._pos = self.maze.start
        self._steps = 0
        return self._pos

    def step(self, action: int) -> tuple[tuple, float, bool, bool]:
        """Returns (new_state, reward, done, timeout)."""
        r, c = self._pos
        dr, dc = _MOVES[action]
        neighbor = (r + dr, c + dc)

        accessible = set(self.maze.neighbors(r, c))
        if neighbor in accessible:
            prev_d = abs(r - self.maze.goal[0]) + abs(c - self.maze.goal[1])
            self._pos = neighbor
            nr, nc = self._pos
            new_d = abs(nr - self.maze.goal[0]) + abs(nc - self.maze.goal[1])
            reward = -0.1 + (prev_d - new_d) * 0.5
        else:
            reward = -1.0  # hit wall

        self._steps += 1
        done = self._pos == self.maze.goal
        if done:
            reward = 100.0
        timeout = self._steps >= self.max_steps
        return self._pos, reward, done, timeout


# ── Shared helpers ────────────────────────────────────────────────────

def _init_q(Q: dict, s: tuple) -> list[float]:
    if s not in Q:
        Q[s] = [0.0] * N_ACTIONS
    return Q[s]


def _greedy(Q: dict, s: tuple) -> int:
    vals = _init_q(Q, s)
    best = max(vals)
    ties = [i for i, v in enumerate(vals) if v == best]
    return random.choice(ties)


def _egreedy(Q: dict, s: tuple, eps: float) -> int:
    if random.random() < eps:
        return random.randrange(N_ACTIONS)
    return _greedy(Q, s)


# ── Four algorithms ───────────────────────────────────────────────────

def run_qlearning(env: GridEnv, n_episodes: int,
                  alpha=0.3, gamma=0.95,
                  eps_start=1.0, eps_decay=0.97, eps_min=0.05):
    Q: dict = {}
    eps = eps_start
    results = []
    for _ in range(n_episodes):
        s = env.reset()
        total_r, steps, reached = 0.0, 0, False
        while True:
            a = _egreedy(Q, s, eps)
            s2, r, done, timeout = env.step(a)
            total_r += r
            steps += 1
            target = r if done else r + gamma * max(_init_q(Q, s2))
            _init_q(Q, s)[a] += alpha * (target - _init_q(Q, s)[a])
            s = s2
            if done:
                reached = True
                break
            if timeout:
                break
        eps = max(eps_min, eps * eps_decay)
        results.append((total_r, steps, reached))
    return results


def run_sarsa(env: GridEnv, n_episodes: int,
              alpha=0.3, gamma=0.95,
              eps_start=1.0, eps_decay=0.97, eps_min=0.05):
    Q: dict = {}
    eps = eps_start
    results = []
    for _ in range(n_episodes):
        s = env.reset()
        a = _egreedy(Q, s, eps)
        total_r, steps, reached = 0.0, 0, False
        while True:
            s2, r, done, timeout = env.step(a)
            total_r += r
            steps += 1
            a2 = _egreedy(Q, s2, eps)
            target = r if done else r + gamma * _init_q(Q, s2)[a2]
            _init_q(Q, s)[a] += alpha * (target - _init_q(Q, s)[a])
            s, a = s2, a2
            if done:
                reached = True
                break
            if timeout:
                break
        eps = max(eps_min, eps * eps_decay)
        results.append((total_r, steps, reached))
    return results


def run_expected_sarsa(env: GridEnv, n_episodes: int,
                       alpha=0.3, gamma=0.95,
                       eps_start=1.0, eps_decay=0.97, eps_min=0.05):
    Q: dict = {}
    eps = eps_start
    results = []
    for _ in range(n_episodes):
        s = env.reset()
        total_r, steps, reached = 0.0, 0, False
        while True:
            a = _egreedy(Q, s, eps)
            s2, r, done, timeout = env.step(a)
            total_r += r
            steps += 1
            if done:
                target = r
            else:
                # expected value over ε-greedy policy
                vals2 = _init_q(Q, s2)
                best2 = max(vals2)
                best_acts = [i for i, v in enumerate(vals2) if v == best2]
                expected = 0.0
                for ai in range(N_ACTIONS):
                    if ai in best_acts:
                        p = (1 - eps) / len(best_acts) + eps / N_ACTIONS
                    else:
                        p = eps / N_ACTIONS
                    expected += p * vals2[ai]
                target = r + gamma * expected
            _init_q(Q, s)[a] += alpha * (target - _init_q(Q, s)[a])
            s = s2
            if done:
                reached = True
                break
            if timeout:
                break
        eps = max(eps_min, eps * eps_decay)
        results.append((total_r, steps, reached))
    return results


def run_dynaq(env: GridEnv, n_episodes: int,
              alpha=0.3, gamma=0.95,
              eps_start=1.0, eps_decay=0.97, eps_min=0.05,
              n_planning=10):
    Q: dict = {}
    model: dict = {}   # (s, a) -> (r, s2)
    eps = eps_start
    results = []
    for _ in range(n_episodes):
        s = env.reset()
        total_r, steps, reached = 0.0, 0, False
        while True:
            a = _egreedy(Q, s, eps)
            s2, r, done, timeout = env.step(a)
            total_r += r
            steps += 1

            # Direct Q-learning update
            target = r if done else r + gamma * max(_init_q(Q, s2))
            _init_q(Q, s)[a] += alpha * (target - _init_q(Q, s)[a])

            # Store in model
            model[(s, a)] = (r, s2, done)

            # Planning: n_planning steps from random memory
            if model:
                mem_keys = list(model.keys())
                for _ in range(n_planning):
                    ps, pa = random.choice(mem_keys)
                    pr, ps2, pdone = model[(ps, pa)]
                    pt = pr if pdone else pr + gamma * max(_init_q(Q, ps2))
                    _init_q(Q, ps)[pa] += alpha * (pt - _init_q(Q, ps)[pa])

            s = s2
            if done:
                reached = True
                break
            if timeout:
                break
        eps = max(eps_min, eps * eps_decay)
        results.append((total_r, steps, reached))
    return results


RUNNERS = {
    "Q-Learning":      run_qlearning,
    "SARSA":           run_sarsa,
    "Expected SARSA":  run_expected_sarsa,
    "Dyna-Q":          run_dynaq,
}

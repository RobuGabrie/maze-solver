"""
core/behaviors.py - Robot behavior implementations for Pioneer P3-DX.

Each behavior exposes:
    step(sensors) -> (v_left, v_right)   — called at ~20 Hz by the worker thread
    get_param_defs()                      — slider definitions for the GUI
    set_param(name, value)                — update a parameter at runtime
    get_status() -> str                   — one-line state string for the GUI

The learning behavior uses tabular Q-learning on discretized proximity states.
"""
import random
from abc import ABC, abstractmethod
from enum import Enum

from .robot import Robot, SensorReading

# Human-readable sensor labels (index 0..15)
SENSOR_LABELS: list[str] = [
    "S00  fata-stanga-ext ",
    "S01  fata-stanga     ",
    "S02  fata-centru-st  ",
    "S03  fata-centru-st  ",
    "S04  fata-centru-dr  ",
    "S05  fata-centru-dr  ",
    "S06  fata-dreapta    ",
    "S07  fata-dreapta-ext",
    "S08  lateral-dreapta ",
    "S09  lateral-dreapta ",
    "S10  spate-dreapta   ",
    "S11  spate-centru    ",
    "S12  spate-centru    ",
    "S13  spate-stanga    ",
    "S14  lateral-stanga  ",
    "S15  lateral-stanga  ",
]

# Control loop timestep (seconds)
DT = 0.05

ParamDef = dict  # {name, label, min, max, default, step}


def _min_dist(sensors: list[SensorReading], indices: tuple[int, ...]) -> float:
    """Minimum distance across a group of sensors; 1.0 if none detected."""
    return min(
        (s.distance for i, s in enumerate(sensors) if i in indices and s.detected),
        default=1.0,
    )


# ------------------------------------------------------------------
# Base class
# ------------------------------------------------------------------

class BehaviorBase(ABC):
    label: str = "Base"

    def __init__(self, robot: Robot) -> None:
        self.robot = robot

    @abstractmethod
    def step(self, sensors: list[SensorReading]) -> tuple[float, float]:
        ...

    def get_param_defs(self) -> list[ParamDef]:
        return []

    def set_param(self, name: str, value: float) -> None:
        if hasattr(self, name):
            setattr(self, name, value)

    def get_status(self) -> str:
        return ""


# ------------------------------------------------------------------
# Braitenberg "Frica" (obstacle avoidance)
# ------------------------------------------------------------------

class BraitenbergBehavior(BehaviorBase):
    label = "Braitenberg (Frica)"

    # Ipsilateral weights for sensors 0-7 (fear / avoidance)
    _WEIGHTS: list[tuple[float, float]] = [
        (+0.5, -0.5), (+1.0, -1.0), (+1.5, -1.5), (+2.0, -2.0),
        (-2.0, +2.0), (-1.5, +1.5), (-1.0, +1.0), (-0.5, +0.5),
    ]

    def __init__(self, robot: Robot) -> None:
        super().__init__(robot)
        self.v_base: float = 3.0
        self.v_max: float = 6.0
        self.k_sensor: float = 6.0
        self._vl = 0.0
        self._vr = 0.0

    def get_param_defs(self) -> list[ParamDef]:
        return [
            {"name": "v_base",    "label": "V_BASE (rad/s)", "min": 0.5, "max": 8.0,  "default": 3.0, "step": 0.5},
            {"name": "v_max",     "label": "V_MAX (rad/s)",  "min": 1.0, "max": 10.0, "default": 6.0, "step": 0.5},
            {"name": "k_sensor",  "label": "K_SENSOR",       "min": 0.5, "max": 15.0, "default": 6.0, "step": 0.5},
        ]

    def step(self, sensors: list[SensorReading]) -> tuple[float, float]:
        vl, vr = self.v_base, self.v_base
        for i, (wl, wr) in enumerate(self._WEIGHTS):
            s = sensors[i]
            if s.detected:
                prox = max(0.0, min(1.0, 1.0 - s.distance))
                vl += self.k_sensor * wl * prox
                vr += self.k_sensor * wr * prox
        self._vl = max(-self.v_max, min(self.v_max, vl))
        self._vr = max(-self.v_max, min(self.v_max, vr))
        return self._vl, self._vr

    def get_status(self) -> str:
        return f"vL={self._vl:+.2f}  vR={self._vr:+.2f}"


# ------------------------------------------------------------------
# Wall following (right-hand wall)
# ------------------------------------------------------------------

class WallFollowBehavior(BehaviorBase):
    label = "Wall Following"

    _RIGHT = (8, 9)
    _FRONT = (3, 4)

    def __init__(self, robot: Robot) -> None:
        super().__init__(robot)
        self.v_base: float = 2.0
        self.target_dist: float = 0.4
        self.k_p: float = 3.0
        self.front_stop: float = 0.4
        self._state = "SEARCH"

    def get_param_defs(self) -> list[ParamDef]:
        return [
            {"name": "v_base",      "label": "V_BASE (rad/s)",     "min": 0.5, "max": 5.0,  "default": 2.0, "step": 0.5},
            {"name": "target_dist", "label": "Target wall dist (m)","min": 0.1, "max": 1.0,  "default": 0.4, "step": 0.05},
            {"name": "k_p",         "label": "K_P",                 "min": 0.5, "max": 10.0, "default": 3.0, "step": 0.5},
            {"name": "front_stop",  "label": "Front stop dist (m)", "min": 0.2, "max": 1.0,  "default": 0.4, "step": 0.05},
        ]

    def step(self, sensors: list[SensorReading]) -> tuple[float, float]:
        d_right = _min_dist(sensors, self._RIGHT)
        d_front = _min_dist(sensors, self._FRONT)

        if d_front < self.front_stop:
            self._state = "TURN LEFT"
            return -self.v_base, self.v_base

        if d_right >= 0.95:
            self._state = "SEARCH"
            return self.v_base, self.v_base * 0.5

        self._state = "FOLLOW"
        err = d_right - self.target_dist
        cap = self.v_base * 1.5
        vl = max(-cap, min(cap, self.v_base + self.k_p * err))
        vr = max(-cap, min(cap, self.v_base - self.k_p * err))
        return vl, vr

    def get_status(self) -> str:
        return self._state


# ------------------------------------------------------------------
# Explorer (wall-follow + recovery state machine)
# ------------------------------------------------------------------

class _ES(Enum):
    WALL_FOLLOW = "WALL_FOLLOW"
    SEARCH      = "SEARCH"
    BACKWARD    = "BACKWARD"
    TURNING     = "TURNING"


class ExplorerBehavior(BehaviorBase):
    label = "Explorer (auto)"

    _RIGHT = (8, 9)
    _FRONT = (2, 3, 4, 5)

    def __init__(self, robot: Robot) -> None:
        super().__init__(robot)
        self.v_base: float = 2.0
        self.v_turn: float = 2.0
        self.target_dist: float = 0.4
        self.k_p: float = 3.0
        self.front_stop: float = 0.35
        self.t_backward: float = 0.8
        self.t_turning: float = 1.4
        self._state = _ES.SEARCH
        self._timer = 0.0
        self._turn_dir = 1

    def get_param_defs(self) -> list[ParamDef]:
        return [
            {"name": "v_base",      "label": "V_BASE (rad/s)",     "min": 0.5, "max": 5.0,  "default": 2.0,  "step": 0.5},
            {"name": "front_stop",  "label": "Front stop (m)",      "min": 0.2, "max": 0.8,  "default": 0.35, "step": 0.05},
            {"name": "target_dist", "label": "Wall target dist (m)","min": 0.1, "max": 1.0,  "default": 0.4,  "step": 0.05},
            {"name": "k_p",         "label": "K_P",                 "min": 0.5, "max": 10.0, "default": 3.0,  "step": 0.5},
        ]

    def _wall_vels(self, d_right: float) -> tuple[float, float]:
        err = d_right - self.target_dist
        cap = self.v_base * 1.5
        return (
            max(-cap, min(cap, self.v_base + self.k_p * err)),
            max(-cap, min(cap, self.v_base - self.k_p * err)),
        )

    def step(self, sensors: list[SensorReading]) -> tuple[float, float]:
        d_front = _min_dist(sensors, self._FRONT)
        d_right = _min_dist(sensors, self._RIGHT)
        vl = vr = self.v_base

        if self._state == _ES.WALL_FOLLOW:
            if d_front < self.front_stop:
                self._state, self._timer, self._turn_dir = _ES.BACKWARD, 0.0, random.choice([-1, 1])
                vl = vr = -self.v_base
            elif d_right >= 0.95:
                self._state, self._timer = _ES.SEARCH, 0.0
                vl, vr = self.v_base, self.v_base * 0.5
            else:
                vl, vr = self._wall_vels(d_right)

        elif self._state == _ES.SEARCH:
            if d_front < self.front_stop:
                self._state, self._timer, self._turn_dir = _ES.BACKWARD, 0.0, random.choice([-1, 1])
                vl = vr = -self.v_base
            elif d_right < 0.95:
                self._state, self._timer = _ES.WALL_FOLLOW, 0.0
                vl, vr = self._wall_vels(d_right)
            else:
                vl, vr = self.v_base, self.v_base * 0.5

        elif self._state == _ES.BACKWARD:
            vl = vr = -self.v_base
            if self._timer >= self.t_backward:
                self._state, self._timer = _ES.TURNING, 0.0

        elif self._state == _ES.TURNING:
            vl = -self.v_turn * self._turn_dir
            vr =  self.v_turn * self._turn_dir
            if self._timer >= self.t_turning:
                self._state, self._timer = _ES.SEARCH, 0.0

        self._timer += DT
        return vl, vr

    def get_status(self) -> str:
        return self._state.value


# ------------------------------------------------------------------
# Stop on obstacle
# ------------------------------------------------------------------

class StopObstacleBehavior(BehaviorBase):
    label = "Oprire la obstacol"

    _FRONT = (2, 3, 4, 5)

    def __init__(self, robot: Robot) -> None:
        super().__init__(robot)
        self.v_forward: float = 2.0
        self.stop_dist: float = 0.5
        self._stopped = False

    def get_param_defs(self) -> list[ParamDef]:
        return [
            {"name": "v_forward", "label": "V_FORWARD (rad/s)", "min": 0.5, "max": 5.0, "default": 2.0, "step": 0.5},
            {"name": "stop_dist", "label": "Stop distance (m)",  "min": 0.1, "max": 1.0, "default": 0.5, "step": 0.05},
        ]

    def step(self, sensors: list[SensorReading]) -> tuple[float, float]:
        d = _min_dist(sensors, self._FRONT)
        if d < self.stop_dist:
            self._stopped = True
            return 0.0, 0.0
        self._stopped = False
        return self.v_forward, self.v_forward

    def get_status(self) -> str:
        return "OPRIT" if self._stopped else "MERS INAINTE"


# ------------------------------------------------------------------
# Q-learning (sensor-based obstacle avoidance)
# ------------------------------------------------------------------

class QLearningBehavior(BehaviorBase):
    label = "Q-learning (autonom)"

    _FRONT = (2, 3, 4, 5)
    _LEFT = (13, 14, 15)
    _RIGHT = (8, 9, 10)

    _ACTION_NAMES = (
        "FORWARD",
        "CURVE_LEFT",
        "CURVE_RIGHT",
        "TURN_LEFT",
        "TURN_RIGHT",
        "BACK_UP",
    )

    def __init__(self, robot: Robot) -> None:
        super().__init__(robot)
        self.alpha: float = 0.25
        self.gamma: float = 0.92
        self.epsilon: float = 0.20
        # 0 = Q-learning, 1 = SARSA
        self.algo: int = 0
        self.epsilon_decay: float = 0.995
        self.epsilon_min: float = 0.05
        self.v_base: float = 7.0
        self.v_turn: float = 5.5
        self.collision_dist: float = 0.18
        self.step_penalty: float = 0.02
        self.forward_reward: float = 0.20
        self.clearance_reward: float = 1.20
        self.collision_penalty: float = 8.0
        self.stuck_limit: int = 35

        self._q_table: dict[tuple[int, int, int], list[float]] = {}
        self._prev_state: tuple[int, int, int] | None = None
        self._prev_action: int | None = None
        self._prev_next_action: int | None = None
        self._last_clearance: float = 1.0
        self._episode = 1
        self._episode_steps = 0
        self._episode_reward = 0.0
        self._last_reward = 0.0
        self._last_action_name = "INIT"
        # stuck detection: track recent positions and recovery state
        self._pos_history: list[tuple[float, float]] = []
        self._stuck_counter: int = 0
        self._recover_steps: int = 0

    def get_param_defs(self) -> list[ParamDef]:
        return [
            {"name": "alpha", "label": "Alpha (learning rate)", "min": 0.05, "max": 0.8, "default": 0.25, "step": 0.05},
            {"name": "gamma", "label": "Gamma (discount)", "min": 0.50, "max": 0.99, "default": 0.92, "step": 0.01},
            {"name": "epsilon", "label": "Epsilon (explore start)", "min": 0.01, "max": 1.0, "default": 0.20, "step": 0.01},
            {"name": "epsilon_decay", "label": "Epsilon decay", "min": 0.90, "max": 0.999, "default": 0.995, "step": 0.001},
            {"name": "epsilon_min", "label": "Epsilon minimum", "min": 0.01, "max": 0.30, "default": 0.05, "step": 0.01},
            {"name": "v_base", "label": "Forward speed (rad/s)", "min": 0.5, "max": 12.0, "default": 7.0, "step": 0.5},
            {"name": "v_turn", "label": "Turn speed (rad/s)", "min": 0.5, "max": 10.0, "default": 5.5, "step": 0.2},
            {"name": "collision_dist", "label": "Collision distance (m)", "min": 0.08, "max": 0.4, "default": 0.18, "step": 0.02},
            {"name": "step_penalty", "label": "Step penalty", "min": 0.0, "max": 0.20, "default": 0.02, "step": 0.01},
            {"name": "forward_reward", "label": "Forward reward", "min": 0.0, "max": 1.0, "default": 0.20, "step": 0.05},
            {"name": "clearance_reward", "label": "Clearance reward", "min": 0.0, "max": 4.0, "default": 1.20, "step": 0.10},
            {"name": "collision_penalty", "label": "Collision penalty", "min": 1.0, "max": 20.0, "default": 8.0, "step": 0.5},
            {"name": "stuck_limit", "label": "Stuck limit (steps)", "min": 10, "max": 120, "default": 35, "step": 1},
            {"name": "algo", "label": "Algo (0=Q,1=SARSA)", "min": 0, "max": 1, "default": 0, "step": 1},
        ]

    def _group_min(self, sensors: list[SensorReading], indices: tuple[int, ...]) -> float:
        return _min_dist(sensors, indices)

    def _bucket(self, distance: float) -> int:
        if distance < 0.22:
            return 0
        if distance < 0.55:
            return 1
        return 2

    def _state_from_sensors(self, sensors: list[SensorReading]) -> tuple[tuple[int, int, int], float, float, float]:
        front = self._group_min(sensors, self._FRONT)
        left = self._group_min(sensors, self._LEFT)
        right = self._group_min(sensors, self._RIGHT)
        return (self._bucket(front), self._bucket(left), self._bucket(right)), front, left, right

    def _q_values(self, state: tuple[int, int, int]) -> list[float]:
        values = self._q_table.get(state)
        if values is None:
            values = [0.0] * len(self._ACTION_NAMES)
            self._q_table[state] = values
        return values

    def _choose_action(self, state: tuple[int, int, int], front: float, left: float, right: float) -> int:
        if front < self.collision_dist:
            if left > right + 0.05:
                return 3
            if right > left + 0.05:
                return 4
            return 5

        if random.random() < self.epsilon:
            return random.randrange(len(self._ACTION_NAMES))

        values = self._q_values(state)
        best_value = max(values)
        best_actions = [i for i, value in enumerate(values) if value == best_value]
        return random.choice(best_actions)

    def _action_velocities(self, action: int) -> tuple[float, float]:
        if action == 0:
            return self.v_base, self.v_base
        if action == 1:
            return self.v_base * 0.55, self.v_base
        if action == 2:
            return self.v_base, self.v_base * 0.55
        if action == 3:
            return -self.v_turn, self.v_turn
        if action == 4:
            return self.v_turn, -self.v_turn
        return -self.v_base * 0.8, -self.v_base * 0.8

    def _reward(self, action: int, front: float, left: float, right: float) -> tuple[float, bool]:
        clearance = min(front, left, right)
        reward = -self.step_penalty

        if action == 0:
            reward += self.forward_reward
        elif action in (1, 2):
            reward -= 0.02
        elif action == 5:
            reward -= 0.03

        reward += self.clearance_reward * max(0.0, clearance - self._last_clearance)

        terminal = False
        if front < self.collision_dist:
            reward -= self.collision_penalty
            terminal = True

        return reward, terminal

    def _learn(self, state: tuple[int, int, int], action: int, reward: float,
               next_state: tuple[int, int, int], terminal: bool, next_action: int | None = None) -> None:
        """Update Q-table. If algo==1 (SARSA) uses next_action value, else Q-learning max.
        """
        q_values = self._q_values(state)
        next_values = self._q_values(next_state)
        if terminal:
            target = reward
        else:
            if getattr(self, "algo", 0) == 1 and next_action is not None:
                target = reward + self.gamma * next_values[next_action]
            else:
                target = reward + self.gamma * max(next_values)
        q_values[action] += self.alpha * (target - q_values[action])

    def step(self, sensors: list[SensorReading], pos: tuple | None = None) -> tuple[float, float]:
        state, front, left, right = self._state_from_sensors(sensors)
        # choose current action first (needed for SARSA learning)
        action = self._choose_action(state, front, left, right)

        # stuck detection: update pos history (use provided pos to avoid extra API call)
        try:
            if pos is not None and len(pos) >= 2:
                px, py = pos[0], pos[1]
            else:
                px, py, _ = self.robot.get_position()
            self._pos_history.append((px, py))
            if len(self._pos_history) > max(10, int(self.stuck_limit)):
                self._pos_history.pop(0)
            # compute net movement over history
            if len(self._pos_history) >= 6:
                dx = self._pos_history[-1][0] - self._pos_history[0][0]
                dy = self._pos_history[-1][1] - self._pos_history[0][1]
                moved = (dx * dx + dy * dy) ** 0.5
                if moved < 0.03:  # less than 3cm over history -> likely stuck
                    self._stuck_counter += 1
                else:
                    self._stuck_counter = 0
        except Exception:
            # cannot read position — ignore
            pass

        # If currently in recovery, force escape maneuvers for some steps
        if self._recover_steps > 0:
            self._recover_steps -= 1
            forced = random.choice([3, 4, 5])  # turn left/right or back up
            chosen = forced
        else:
            chosen = action

        # If stuck detected, initiate recovery
        if self._stuck_counter >= max(3, int(self.stuck_limit / 10)):
            self._recover_steps = max(6, int(self.stuck_limit / 6))
            self._stuck_counter = 0
            chosen = 5  # back up first

        # Now perform learning for previous step using current chosen action as next_action
        if self._prev_state is not None and self._prev_action is not None:
            reward, terminal = self._reward(self._prev_action, front, left, right)
            # next_action used for SARSA (use chosen)
            self._learn(self._prev_state, self._prev_action, reward, state, terminal, next_action=chosen)
            self._episode_reward += reward
            self._last_reward = reward

            if terminal:
                self._episode += 1
                self._episode_steps = 0
                self._episode_reward = 0.0
                self._prev_state = None
                self._prev_action = None
                self._prev_next_action = None
                self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
            else:
                self._episode_steps += 1

        # record this step as previous for next call
        self._prev_state = state
        self._prev_action = chosen
        self._prev_next_action = None
        self._last_clearance = min(front, left, right)
        self._last_action_name = self._ACTION_NAMES[chosen]

        if self._episode_steps and self._episode_steps % max(1, int(self.stuck_limit)) == 0:
            self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

        return self._action_velocities(chosen)

    def get_status(self) -> str:
        return (
            f"ep={self._episode:03d} step={self._episode_steps:03d} "
            f"r={self._episode_reward:+.2f} eps={self.epsilon:.2f} action={self._last_action_name}"
        )


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------

BEHAVIORS: dict[str, type[BehaviorBase]] = {
    "q_learning":  QLearningBehavior,
    "braitenberg": BraitenbergBehavior,
    "wall_follow": WallFollowBehavior,
    "explorer":    ExplorerBehavior,
    "stop":        StopObstacleBehavior,
}

"""
Legacy baseline maze-solving algorithms for Pioneer P3-DX in CoppeliaSim.

These controllers remain in the project as comparison baselines for the
Q-learning agent used in the main GUI.

All algorithms share the same interface:
    algo.run(duration)   – blocking loop
    algo.step()          – single 20 Hz control tick, returns False to stop

Algorithms implemented
──────────────────────
1. RightHandRule   – keep right wall always on the right
2. LeftHandRule    – keep left wall always on the left
3. PledgeAlgorithm – right-hand rule + turn counter (handles isolated obstacles)
4. TremauxAlgorithm – DFS with passage marking (guaranteed to find exit)
"""
import math
import time
from abc import ABC, abstractmethod

from robot import Robot, DT, V_BASE, V_TURN, SENSOR_MAX
from robot import FRONT_SENSORS, RIGHT_SENSORS, LEFT_SENSORS
from grid_map import GridMap

# ── shared parameters ─────────────────────────────────────────────────────────

FRONT_STOP = 0.40      # m – minimum front clearance before a turn is forced
SIDE_TARGET = 0.40     # m – desired wall-following distance
K_P = 3.0              # proportional gain for wall-following P-controller
T_TURN_90 = 1.40       # seconds for a ~90° point turn at V_TURN = 2.0 rad/s
SIDE_OPEN = 0.90       # threshold: side sensor > this → no wall on that side


# ── shared helpers ────────────────────────────────────────────────────────────

def _p_follow_right(dist_right: float) -> tuple[float, float]:
    """P-controller: maintain SIDE_TARGET distance from right wall."""
    err = dist_right - SIDE_TARGET
    cap = V_BASE * 1.5
    return (
        max(-cap, min(cap, V_BASE + K_P * err)),
        max(-cap, min(cap, V_BASE - K_P * err)),
    )


def _p_follow_left(dist_left: float) -> tuple[float, float]:
    """P-controller: maintain SIDE_TARGET distance from left wall."""
    err = dist_left - SIDE_TARGET
    cap = V_BASE * 1.5
    return (
        max(-cap, min(cap, V_BASE - K_P * err)),
        max(-cap, min(cap, V_BASE + K_P * err)),
    )


# ── base class ────────────────────────────────────────────────────────────────

class Algorithm(ABC):
    def __init__(self, robot: Robot, grid_map: GridMap | None = None):
        self.robot = robot
        self.grid_map = grid_map

    @abstractmethod
    def step(self) -> bool:
        """One control tick. Returns False to request stop."""

    def run(self, duration: float = 120.0) -> None:
        start = time.time()
        try:
            while time.time() - start < duration:
                if not self.step():
                    break
                time.sleep(DT)
        except KeyboardInterrupt:
            pass
        finally:
            self.robot.stop()


# ── 1. Right-Hand Rule ────────────────────────────────────────────────────────

class RightHandRule(Algorithm):
    """
    Classic right-hand rule.
    Priority: if front blocked → turn left; if no right wall → turn right; else follow.
    Works for any simply-connected maze (no isolated obstacles).
    """

    def step(self) -> bool:
        df = self.robot.read_group(FRONT_SENSORS)
        dr = self.robot.read_group(RIGHT_SENSORS)
        if self.grid_map:
            self.robot.update_map(self.grid_map)
        rx, ry = self.robot.position()

        if df < FRONT_STOP:
            self.robot.set_velocity(-V_TURN, V_TURN)     # turn left
            print(f"[RHR] TURN_LEFT    front={df:.2f}m  pos=({rx:.2f},{ry:.2f})")
        elif dr > SIDE_OPEN:
            self.robot.set_velocity(V_BASE, V_BASE * 0.3)  # curve right to find wall
            print(f"[RHR] SEEK_RIGHT   right={dr:.2f}m  pos=({rx:.2f},{ry:.2f})")
        else:
            vl, vr = _p_follow_right(dr)
            self.robot.set_velocity(vl, vr)
            print(f"[RHR] FOLLOW       right={dr:.2f}m  vL={vl:+.2f}  vR={vr:+.2f}")
        return True


# ── 2. Left-Hand Rule ─────────────────────────────────────────────────────────

class LeftHandRule(Algorithm):
    """
    Mirror of the right-hand rule.
    Priority: if front blocked → turn right; if no left wall → turn left; else follow.
    Explores the opposite side of the maze from RHR.
    """

    def step(self) -> bool:
        df = self.robot.read_group(FRONT_SENSORS)
        dl = self.robot.read_group(LEFT_SENSORS)
        if self.grid_map:
            self.robot.update_map(self.grid_map)
        rx, ry = self.robot.position()

        if df < FRONT_STOP:
            self.robot.set_velocity(V_TURN, -V_TURN)      # turn right
            print(f"[LHR] TURN_RIGHT   front={df:.2f}m  pos=({rx:.2f},{ry:.2f})")
        elif dl > SIDE_OPEN:
            self.robot.set_velocity(V_BASE * 0.3, V_BASE)  # curve left to find wall
            print(f"[LHR] SEEK_LEFT    left={dl:.2f}m   pos=({rx:.2f},{ry:.2f})")
        else:
            vl, vr = _p_follow_left(dl)
            self.robot.set_velocity(vl, vr)
            print(f"[LHR] FOLLOW       left={dl:.2f}m   vL={vl:+.2f}  vR={vr:+.2f}")
        return True


# ── 3. Pledge Algorithm ───────────────────────────────────────────────────────

class PledgeAlgorithm(Algorithm):
    """
    Pledge (1981): right-hand rule augmented with a cumulative turn counter.

    Counter semantics (quarter-turn units):
        +1 per 90° right turn, -1 per 90° left turn.
    When counter == 0 after completing a wall-following turn, the robot leaves
    the wall and resumes straight travel. This breaks out of loops that occur
    with isolated (disconnected) obstacles.
    """

    def __init__(self, robot: Robot, grid_map: GridMap | None = None):
        super().__init__(robot, grid_map)
        self._count = 0           # cumulative turn counter
        self._wall_mode = False   # True while following a wall
        self._turning = False
        self._turn_dir = 0        # +1=right, -1=left
        self._turn_t = 0.0

    def _start_turn(self, direction: int) -> None:
        self._turning = True
        self._turn_dir = direction
        self._turn_t = 0.0

    def step(self) -> bool:
        df = self.robot.read_group(FRONT_SENSORS)
        dr = self.robot.read_group(RIGHT_SENSORS)
        if self.grid_map:
            self.robot.update_map(self.grid_map)
        rx, ry = self.robot.position()

        # ── finish ongoing turn ──────────────────────────────────────────
        if self._turning:
            self._turn_t += DT
            self.robot.set_velocity(-V_TURN * self._turn_dir, V_TURN * self._turn_dir)
            if self._turn_t >= T_TURN_90:
                self._turning = False
                self._count += self._turn_dir
                print(f"[PLG] turn_done  count={self._count}")
                if self._count == 0 and self._wall_mode:
                    self._wall_mode = False
                    print(f"[PLG] EXIT_WALL  count back to 0")
            return True

        # ── straight travel mode ─────────────────────────────────────────
        if not self._wall_mode:
            if df < FRONT_STOP:
                self._wall_mode = True
                self._start_turn(+1)          # enter wall-mode with a right turn
                print(f"[PLG] HIT_WALL   front={df:.2f}m → start wall-follow, turn right")
            else:
                self.robot.set_velocity(V_BASE, V_BASE)
                print(f"[PLG] STRAIGHT   pos=({rx:.2f},{ry:.2f})  count={self._count}")
            return True

        # ── wall-following mode ──────────────────────────────────────────
        if dr > SIDE_OPEN and df >= FRONT_STOP:
            # Open gap on right: step right (count decreases toward 0)
            self._start_turn(+1)
            print(f"[PLG] OPEN_RIGHT  count={self._count} → turn right")
        elif df < FRONT_STOP:
            # Blocked: turn left
            self._start_turn(-1)
            print(f"[PLG] BLOCKED     count={self._count} → turn left")
        else:
            vl, vr = _p_follow_right(dr)
            self.robot.set_velocity(vl, vr)
            print(f"[PLG] WALL_FOLLOW right={dr:.2f}m  count={self._count}")
        return True


# ── 4. Trémaux Algorithm ──────────────────────────────────────────────────────

class TremauxAlgorithm(Algorithm):
    """
    Trémaux's algorithm (DFS with passage marking).

    Each cell carries a visit count.  At every decision point the robot
    chooses the direction with the *fewest visits* (0 preferred, then 1).
    Directions with ≥2 visits are never re-entered.
    Guaranteed to find any exit in a finite-length maze.

    Decision points are detected when:
      - the front is clear AND at least one side is open  (junction / T-cross)
      - the front is blocked                               (dead-end / corner)
    """

    _STEP = GridMap.CELL_SIZE * 2  # lookahead distance for visit probing

    def __init__(self, robot: Robot, grid_map: GridMap):
        super().__init__(robot, grid_map)
        self._turning = False
        self._turn_dir = 0    # +1=right, -1=left, 2=180°
        self._turn_t = 0.0
        self._in_corridor = False

    def _start_turn(self, direction: int) -> None:
        self._turning = True
        self._turn_dir = direction
        self._turn_t = 0.0

    def _visits_ahead(self, angle_offset: float = 0.0) -> int:
        """Visit count of the cell two steps ahead in direction theta+angle_offset."""
        rx, ry = self.robot.position()
        theta = self.robot.orientation() + angle_offset
        px = rx + self._STEP * math.cos(theta)
        py = ry + self._STEP * math.sin(theta)
        return self.grid_map.get_visits(px, py)

    def _best_turn(self, df: float, dl: float, dr: float) -> int:
        """Return best turn direction (+1=right, -1=left, 0=straight, 2=reverse)."""
        options: list[tuple[int, int, float]] = []  # (turn_dir, visits, clearance)

        if df >= FRONT_STOP:
            options.append((0, self._visits_ahead(0.0), df))
        if dr >= SIDE_OPEN:
            options.append((+1, self._visits_ahead(-math.pi / 2), dr))
        if dl >= SIDE_OPEN:
            options.append((-1, self._visits_ahead(+math.pi / 2), dl))

        if not options:
            return 2  # dead-end: reverse

        # Sort: fewer visits first, more clearance as tiebreaker
        options.sort(key=lambda t: (t[1], -t[2]))
        best_dir, best_visits, _ = options[0]

        if best_visits >= 2:
            return 2  # all options exhausted: reverse
        return best_dir

    def _is_decision_point(self, df: float, dl: float, dr: float) -> bool:
        """True when the robot should re-evaluate its heading."""
        blocked = df < FRONT_STOP
        open_side = dl > SIDE_OPEN or dr > SIDE_OPEN
        return blocked or (not self._in_corridor and open_side)

    def step(self) -> bool:
        df = self.robot.read_group(FRONT_SENSORS)
        dr = self.robot.read_group(RIGHT_SENSORS)
        dl = self.robot.read_group(LEFT_SENSORS)
        self.robot.update_map(self.grid_map)
        rx, ry = self.robot.position()
        visits = self.grid_map.get_visits(rx, ry)

        # ── finish ongoing turn ──────────────────────────────────────────
        if self._turning:
            self._turn_t += DT
            duration = T_TURN_90 * (2 if self._turn_dir == 2 else 1)
            actual_dir = -1 if self._turn_dir == 2 else self._turn_dir
            self.robot.set_velocity(-V_TURN * actual_dir, V_TURN * actual_dir)
            if self._turn_t >= duration:
                self._turning = False
                self._in_corridor = False
                print(f"[TRM] turn_done  pos=({rx:.2f},{ry:.2f})")
            return True

        # ── decision point? ──────────────────────────────────────────────
        if self._is_decision_point(df, dl, dr):
            choice = self._best_turn(df, dl, dr)
            print(
                f"[TRM] DECISION  front={df:.2f} left={dl:.2f} right={dr:.2f}"
                f"  visits={visits}  → dir={choice}"
            )
            if choice == 0:
                # Continue straight, no turn needed
                vl, vr = self._corridor_velocities(dr, dl)
                self.robot.set_velocity(vl, vr)
                self._in_corridor = True
            else:
                self._start_turn(choice)
            return True

        # ── corridor travel ───────────────────────────────────────────────
        vl, vr = self._corridor_velocities(dr, dl)
        self.robot.set_velocity(vl, vr)
        self._in_corridor = True
        print(
            f"[TRM] CORRIDOR  right={dr:.2f} left={dl:.2f}"
            f"  visits={visits}  pos=({rx:.2f},{ry:.2f})"
        )
        return True

    def _corridor_velocities(self, dr: float, dl: float) -> tuple[float, float]:
        """Wall-follow whichever side has a nearby wall; go straight if both open."""
        if dr < SIDE_OPEN and dl < SIDE_OPEN:
            # Both walls present: follow the closer one
            if dr <= dl:
                return _p_follow_right(dr)
            return _p_follow_left(dl)
        if dr < SIDE_OPEN:
            return _p_follow_right(dr)
        if dl < SIDE_OPEN:
            return _p_follow_left(dl)
        return V_BASE, V_BASE  # open corridor: go straight

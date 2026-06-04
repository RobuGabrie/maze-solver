"""Pioneer P3-DX interface for CoppeliaSim via ZMQ Remote API."""
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grid_map import GridMap

SENSOR_MAX = 1.0   # metres - max reliable range
DT = 0.05          # seconds - control loop period (20 Hz)
V_BASE = 2.0       # rad/s
V_TURN = 2.0       # rad/s
V_MAX = 4.0        # rad/s

FRONT_SENSORS = [2, 3, 4, 5]
RIGHT_SENSORS = [8, 9]
LEFT_SENSORS = [14, 15]


class Robot:
    """Wraps CoppeliaSim handles for Pioneer P3-DX motors and sensors."""

    def __init__(self, sim):
        self.sim = sim
        self._robot = sim.getObject("/PioneerP3DX")
        self._left = sim.getObject("/PioneerP3DX/leftMotor")
        self._right = sim.getObject("/PioneerP3DX/rightMotor")
        self._sensors = [
            sim.getObject(f"/PioneerP3DX/ultrasonicSensor[{i}]")
            for i in range(16)
        ]

    # ── state ─────────────────────────────────────────────────────────────

    def position(self) -> tuple[float, float]:
        p = self.sim.getObjectPosition(self._robot, self.sim.handle_world)
        return p[0], p[1]

    def orientation(self) -> float:
        """Yaw angle in radians (world Z-axis rotation)."""
        o = self.sim.getObjectOrientation(self._robot, self.sim.handle_world)
        return o[2]

    # ── sensing ───────────────────────────────────────────────────────────

    def read_sensor(self, idx: int) -> tuple[bool, float]:
        result, dist, *_ = self.sim.readProximitySensor(self._sensors[idx])
        detected = bool(result)
        return detected, (dist if detected else SENSOR_MAX)

    def read_group(self, indices: list[int]) -> float:
        """Minimum detected distance from a group of sensors."""
        min_d = SENSOR_MAX
        for idx in indices:
            det, d = self.read_sensor(idx)
            if det and d < min_d:
                min_d = d
        return min_d

    def read_all(self) -> list[tuple[bool, float]]:
        return [self.read_sensor(i) for i in range(16)]

    def sensor_world_pos(self, idx: int) -> tuple[float, float]:
        p = self.sim.getObjectPosition(self._sensors[idx], self.sim.handle_world)
        return p[0], p[1]

    # ── actuation ─────────────────────────────────────────────────────────

    def set_velocity(self, v_left: float, v_right: float) -> None:
        self.sim.setJointTargetVelocity(self._left, v_left)
        self.sim.setJointTargetVelocity(self._right, v_right)

    def stop(self) -> None:
        self.set_velocity(0.0, 0.0)

    # ── mapping ───────────────────────────────────────────────────────────

    def update_map(self, grid_map: "GridMap") -> None:
        """Mark current cell free, increment visit count, project sensor walls."""
        rx, ry = self.position()
        grid_map.mark_free(rx, ry)
        grid_map.visit(rx, ry)

        for i in range(16):
            detected, dist = self.read_sensor(i)
            if not detected:
                continue
            sx, sy = self.sensor_world_pos(i)
            # Direction: from robot centre toward sensor (sensors point outward)
            dx, dy = sx - rx, sy - ry
            length = math.hypot(dx, dy) or 1e-9
            dir_x, dir_y = dx / length, dy / length
            wx, wy = sx + dir_x * dist, sy + dir_y * dist
            grid_map.mark_ray(sx, sy, wx, wy)

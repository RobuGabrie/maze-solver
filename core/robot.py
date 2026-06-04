"""
core/robot.py - CoppeliaSim robot interface for Pioneer P3-DX.
"""
from dataclasses import dataclass

from coppeliasim_zmqremoteapi_client import RemoteAPIClient


@dataclass
class SensorReading:
    detected: bool
    distance: float  # meters; SENSOR_MAX when nothing detected


class Robot:
    SENSOR_MAX = 1.0
    N_SENSORS = 16

    def __init__(self) -> None:
        self._client: RemoteAPIClient | None = None
        self.sim = None
        self._robot_handle: int | None = None
        self._left_motor: int | None = None
        self._right_motor: int | None = None
        self._sensors: list[int] = []
        self._mobile_handles: list[int] = []
        self._mobile_threads: list = []
        self._mobile_stop = False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, host: str = "localhost", port: int = 23000) -> None:
        """Connect to CoppeliaSim. Does NOT require a robot in the scene."""
        self._client = RemoteAPIClient(host=host, port=port)
        self.sim = self._client.require("sim")

    def load_robot(self) -> None:
        """Load Pioneer P3-DX handles. Call this before starting a behavior."""
        self._robot_handle = self.sim.getObject("/PioneerP3DX")
        self._left_motor = self.sim.getObject("/PioneerP3DX/leftMotor")
        self._right_motor = self.sim.getObject("/PioneerP3DX/rightMotor")
        self._sensors = [
            self.sim.getObject(f"/PioneerP3DX/ultrasonicSensor[{i}]")
            for i in range(self.N_SENSORS)
        ]

    @property
    def robot_loaded(self) -> bool:
        return self._robot_handle is not None

    def disconnect(self) -> None:
        if self.sim:
            try:
                self.set_velocity(0.0, 0.0)
            except Exception:
                pass
        self._client = None
        self.sim = None
        self._sensors = []

    @property
    def connected(self) -> bool:
        return self.sim is not None

    # ------------------------------------------------------------------
    # Simulation lifecycle
    # ------------------------------------------------------------------

    def start_simulation(self) -> None:
        self.sim.startSimulation()

    def stop_simulation(self) -> None:
        try:
            self.set_velocity(0.0, 0.0)
        except Exception:
            pass
        self.sim.stopSimulation()

    # ------------------------------------------------------------------
    # Control & sensing
    # ------------------------------------------------------------------

    def set_velocity(self, left: float, right: float) -> None:
        self.sim.setJointTargetVelocity(self._left_motor, left)
        self.sim.setJointTargetVelocity(self._right_motor, right)

    def read_sensors(self) -> list[SensorReading]:
        readings: list[SensorReading] = []
        for s in self._sensors:
            result, dist, *_ = self.sim.readProximitySensor(s)
            readings.append(SensorReading(
                detected=bool(result),
                distance=float(dist) if bool(result) else self.SENSOR_MAX,
            ))
        return readings

    def get_position(self) -> tuple[float, float, float]:
        pos = self.sim.getObjectPosition(self._robot_handle, self.sim.handle_world)
        return float(pos[0]), float(pos[1]), float(pos[2])

    def get_orientation(self) -> float:
        """Returns heading (yaw / Z-axis rotation) in radians, world frame."""
        euler = self.sim.getObjectOrientation(self._robot_handle, self.sim.handle_world)
        return float(euler[2])

    def get_sim_time(self) -> float:
        return float(self.sim.getSimulationTime())

    # ------------------------------------------------------------------
    # Mobile obstacles helpers
    # ------------------------------------------------------------------

    def spawn_mobile_objects(self, mobiles: list[dict], rows: int, cols: int, cell_size: float) -> None:
        """
        Creează cilindri mov în CoppeliaSim pentru fiecare obstacol mobil.
        Setează obiectele ca fiind STATICE (nu cad) și RESPONDABLE (pot fi detectate).
        """
        if not self.connected or not hasattr(self, 'sim'):
            return
        
        self._mobile_handles = getattr(self, '_mobile_handles', [])
        
        for i, mob in enumerate(mobiles):
            r, c = mob["cell"]
            x = (c * cell_size) + (cell_size / 2.0)
            y = (r * cell_size) + (cell_size / 2.0)
            
            try:
                # 8 reprezintă flag-ul pentru 'Respondable' în createPrimitiveShape
                handle = self.sim.createPrimitiveShape(2, [cell_size*0.7, cell_size*0.7, 0.4], 8)
                
                # Pozitionam obstacolul deasupra podelei
                self.sim.setObjectPosition(handle, self.sim.handle_world, [x, y, 0.2])
                
                # Il facem mov
                self.sim.setObjectColor(handle, 0, self.sim.colorcomponent_ambient_diffuse, [0.6, 0.1, 0.6])
                
                # --- SETĂRILE CRITICE PENTRU FIZICĂ ---
                # 1. Îl facem STATIC (ignoră gravitația, stă în aer dacă e nevoie, controlat doar de tine)
                self.sim.setObjectInt32Param(handle, self.sim.shapeintparam_static, 1)
                
                # 2. Ne asigurăm că este RESPONDABLE (senzorii și robotul se vor bloca în el)
                self.sim.setObjectInt32Param(handle, self.sim.shapeintparam_respondable, 1)
                # --------------------------------------
                
                self._mobile_handles.append({
                    "handle": handle,
                    "path": mob.get("path", []),
                    "speed": mob.get("speed", 0.25)
                })
            except Exception as e:
                print(f"Eroare la crearea obstacolului în CoppeliaSim: {e}")

    def start_mobile_objects(self, mobiles: list[dict], rows: int, cols: int, cell_size: float) -> None:
        """O funcție stub (goală) pentru a preveni erorile din app.py, dacă simularea mișcării 
           se face intern în CoppeliaSim sau o vei adăuga tu ulterior."""
        pass

    def stop_mobile_objects(self) -> None:
        """
        Șterge obstacolele mobile din scenă la oprire sau curățare.
        """
        if not self.connected or not hasattr(self, 'sim'):
            return
        
        if hasattr(self, '_mobile_handles'):
            for obj in self._mobile_handles:
                try:
                    self.sim.removeObject(obj["handle"])
                except Exception:
                    pass
            self._mobile_handles.clear()

            
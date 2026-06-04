"""
Legacy reactive explorer for Pioneer P3-DX in CoppeliaSim.
=========================================================

This script keeps the classic wall-following / Trémaux baselines available
for comparison, while the main project focus is the Q-learning controller in
the GUI.

Usage
-----
    python maze_explorer.py --algorithm right    # Right-Hand Rule
    python maze_explorer.py --algorithm left     # Left-Hand Rule
    python maze_explorer.py --algorithm pledge   # Pledge Algorithm
    python maze_explorer.py --algorithm tremaux  # Trémaux (DFS)
    python maze_explorer.py -a pledge -d 180 --save-map

Requirements
------------
    CoppeliaSim must be open with the Pioneer P3-DX scene loaded and
    the simulation RUNNING (▶) before launching this script.

    pip install coppeliasim-zmqremoteapi-client matplotlib numpy
"""
import argparse
import time

from coppeliasim_zmqremoteapi_client import RemoteAPIClient

from robot import Robot, DT
from grid_map import GridMap
from algorithms import RightHandRule, LeftHandRule, PledgeAlgorithm, TremauxAlgorithm

ALGORITHMS = {
    "right":   RightHandRule,
    "left":    LeftHandRule,
    "pledge":  PledgeAlgorithm,
    "tremaux": TremauxAlgorithm,
}

DESCRIPTIONS = {
    "right":   "Right-Hand Rule      – follow right wall (works on simply-connected mazes)",
    "left":    "Left-Hand Rule       – follow left wall  (explores opposite side)",
    "pledge":  "Pledge Algorithm     – right-hand rule + turn counter (handles isolated obstacles)",
    "tremaux": "Trémaux / DFS        – mark passages, prefer least-visited (guaranteed to find exit)",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Legacy reactive explorer – Pioneer P3-DX in CoppeliaSim",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {k:8s}  {v}" for k, v in DESCRIPTIONS.items()),
    )
    p.add_argument(
        "--algorithm", "-a",
        choices=list(ALGORITHMS),
        default="right",
        metavar="ALGO",
        help="Algorithm: right | left | pledge | tremaux  (default: right)",
    )
    p.add_argument(
        "--duration", "-d",
        type=float,
        default=120.0,
        help="Max run time in seconds (default: 120)",
    )
    p.add_argument(
        "--save-map",
        action="store_true",
        help="Save occupancy grid as map_<algo>.png after run",
    )
    p.add_argument(
        "--port",
        type=int,
        default=23000,
        help="CoppeliaSim ZMQ port (default: 23000)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print("Connecting to CoppeliaSim…")
    client = RemoteAPIClient(port=args.port)
    sim = client.require("sim")
    version = sim.getInt32Param(sim.intparam_program_version)
    print(f"Connected. CoppeliaSim version (encoded): {version}\n")

    robot = Robot(sim)
    grid_map = GridMap()

    AlgorithmClass = ALGORITHMS[args.algorithm]
    algo = AlgorithmClass(robot, grid_map)

    print(f"Algorithm : {DESCRIPTIONS[args.algorithm]}")
    print(f"Duration  : {args.duration}s")
    print(f"Save map  : {args.save_map}")
    print("\nStarting simulation… (Ctrl+C to stop early)\n")

    sim.startSimulation()
    trajectory: list[tuple[float, float]] = []
    start_wall = time.time()

    try:
        while time.time() - start_wall < args.duration:
            if not algo.step():
                break
            trajectory.append(robot.position())
            time.sleep(DT)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        robot.stop()
        sim.stopSimulation()
        elapsed = time.time() - start_wall
        print(f"\nElapsed: {elapsed:.1f}s  |  {len(trajectory)} position samples")

        if args.save_map and trajectory:
            fname = f"map_{args.algorithm}.png"
            grid_map.save_png(fname, trajectory)
            print(f"Map saved: {fname}")


if __name__ == "__main__":
    main()

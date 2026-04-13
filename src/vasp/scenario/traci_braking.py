#!/usr/bin/env python3
"""
TraCI script to trigger leader braking events in SUMO.
Two legitimate hard-braking events for FP evaluation.

  Event 1: t=40-42s, a=-4.0 m/s^2 (vehicle_0 = leader)
  Event 2: t=80-81.5s, a=-3.5 m/s^2

Usage (standalone SUMO test):
  sumo -c highway.sumocfg --remote-port 8813 &
  python traci_braking.py

Usage (with VEINS/VASP):
  These events are triggered in the C++ application layer instead.
  See vasp_integration/04_integration_hooks.md for details.
"""

import os
import sys
import time

# Add SUMO tools to path
if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))
else:
    sys.exit("Please set SUMO_HOME environment variable")

import traci

# -- Configuration matching paper Section 6.2 --
LEADER_ID = "vehicle_0"
BRAKING_EVENTS = [
    # (start_time, end_time, deceleration)
    (40.0, 42.0, -4.0),   # Event 1: hard brake
    (80.0, 81.5, -3.5),   # Event 2: moderate hard brake
]
SIM_END = 120.0
STEP_LENGTH = 0.01  # 10ms physics step


def run():
    traci.start([
        "sumo",
        "-c", "highway.sumocfg",
        "--step-length", str(STEP_LENGTH),
        "--collision.action", "warn",
        "--no-step-log",
    ])

    print("=" * 60)
    print("  SUMO + TraCI: Leader Braking Events")
    print("=" * 60)

    step = 0
    braking_active = False

    while traci.simulation.getTime() < SIM_END:
        t = traci.simulation.getTime()

        # Check if leader exists
        if LEADER_ID in traci.vehicle.getIDList():
            # Check braking events
            current_brake = None
            for t_start, t_end, decel in BRAKING_EVENTS:
                if t_start <= t <= t_end:
                    current_brake = decel
                    break

            if current_brake is not None:
                if not braking_active:
                    print(f"  [{t:.1f}s] Leader braking: a={current_brake} m/s^2")
                    braking_active = True
                # Apply deceleration via slowDown
                current_speed = traci.vehicle.getSpeed(LEADER_ID)
                target_speed = max(0.0, current_speed + current_brake * STEP_LENGTH)
                traci.vehicle.slowDown(LEADER_ID, target_speed, int(STEP_LENGTH * 1000))
            else:
                if braking_active:
                    print(f"  [{t:.1f}s] Leader braking ended")
                    braking_active = False
                    # Resume normal driving
                    traci.vehicle.setSpeed(LEADER_ID, -1)  # return to IDM control

        traci.simulationStep()
        step += 1

        # Progress
        if step % 10000 == 0:
            n_vehs = len(traci.vehicle.getIDList())
            leader_v = traci.vehicle.getSpeed(LEADER_ID) if LEADER_ID in traci.vehicle.getIDList() else 0
            print(f"  [{t:.1f}s] {n_vehs} vehicles, leader v={leader_v:.1f} m/s")

    traci.close()
    print(f"\n[OK]  Simulation complete ({step} steps)")


if __name__ == '__main__':
    run()

#!/usr/bin/env python3
"""
generate_route_variants.py
--------------------------
Generates N route file variants for multi-seed experiments.

Variation sources per seed:
  1. Initial vehicle speeds: randomized (25 +/- 2 m/s)
  2. Inter-vehicle gaps: randomized (30 +/- 3 m)
  3. sigma=0.5 + speedDev=0.1 -> SUMO adds stochastic noise to IDM

Usage:
    python3 generate_route_variants.py [N_seeds] [sigma]
    python3 generate_route_variants.py 5 0.5     # recommended
    python3 generate_route_variants.py 5 0.0     # deterministic (original)
"""

import os, sys, shutil
import numpy as np

N_VEHICLES = 20
NOMINAL_SPEED = 25.0
SPEED_STD = 2.0
SPEED_MIN = 18.0
SPEED_MAX = 30.0
LEAD_POS = 600.0
NOMINAL_GAP = 30.0
GAP_STD = 3.0
GAP_MIN = 20.0
GAP_MAX = 40.0

TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<routes>
    <vType id="idm_car" accel="1.4" decel="2.0" sigma="{sigma}"
           length="5.0" minGap="2.0" maxSpeed="33.33"
           speedFactor="1.0" speedDev="0.1"
           carFollowModel="IDM" tau="1.5" guiShape="passenger" color="0,128,255"/>

    <route id="highway_route" edges="highway"/>

{vehicles}
</routes>
"""

VEHICLE_TEMPLATE = '    <vehicle id="vehicle_{idx}" type="idm_car" route="highway_route"\n             depart="0" departPos="{pos:.1f}" departSpeed="{spd:.1f}"/>'


def generate_variant(seed, sigma):
    rng = np.random.RandomState(seed * 1000 + 42)
    speeds = np.clip(rng.normal(NOMINAL_SPEED, SPEED_STD, N_VEHICLES), SPEED_MIN, SPEED_MAX)
    positions = [LEAD_POS]
    for i in range(1, N_VEHICLES):
        gap = np.clip(rng.normal(NOMINAL_GAP, GAP_STD), GAP_MIN, GAP_MAX)
        positions.append(positions[-1] - gap)
    if min(positions) < 10:
        positions = [p + (10 - min(positions)) for p in positions]
    vehicles = [VEHICLE_TEMPLATE.format(idx=i, pos=positions[i], spd=speeds[i]) for i in range(N_VEHICLES)]
    return TEMPLATE.format(sigma=f"{sigma:.1f}", vehicles='\n'.join(vehicles))


def main():
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    sigma = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    
    print(f"Generating {n_seeds} route variants (sigma={sigma}, speedDev=0.1)")
    for s in range(n_seeds):
        content = generate_variant(s, sigma)
        path = f'highway_seed{s}.rou.xml'
        with open(path, 'w') as f:
            f.write(content)
        rng = np.random.RandomState(s * 1000 + 42)
        speeds = np.clip(rng.normal(NOMINAL_SPEED, SPEED_STD, N_VEHICLES), SPEED_MIN, SPEED_MAX)
        print(f"  Seed {s}: avg_speed={speeds.mean():.1f} m/s -> {path}")
    
    if not os.path.exists('highway_original.rou.xml') and os.path.exists('highway.rou.xml'):
        shutil.copy2('highway.rou.xml', 'highway_original.rou.xml')
        print(f"\n  Backed up: highway.rou.xml -> highway_original.rou.xml")
    print(f"\n  Done! Next: ./run_multi_seed.sh")

if __name__ == '__main__':
    main()

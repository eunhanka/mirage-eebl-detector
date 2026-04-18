#!/bin/bash
# =============================================================================
# run_single_seed.sh
#
# Run every experiment configuration (baseline + attacks + ablations) for a
# single seed. Use this for a quick end-to-end reproduction; a full 5-seed
# run is ~5x longer — see run_multi_seed.sh for that.
#
# Usage:
#   ./scripts/run_single_seed.sh [seed]
#
# Default seed is 0. Results land in
#   /opt/mirage/veins-5.2/src/vasp/scenario/results/detlog-<config>-<seed>-*.csv
# Then verify with:
#   ./scripts/verify_results.py --seeds <seed>
# =============================================================================

set -euo pipefail

SEED="${1:-0}"
MIRAGE_PREFIX="${MIRAGE_PREFIX:-/opt/mirage}"
VEINS_DIR="${MIRAGE_PREFIX}/veins-5.2"
SCENARIO_DIR="${VEINS_DIR}/src/vasp/scenario"
SUMO_PORT="${SUMO_PORT:-9999}"
SIM_TIME="${SIM_TIME:-120s}"

# Colors
c_info='\033[0;36m'; c_ok='\033[0;32m'; c_fail='\033[0;31m'; c_rst='\033[0m'
log()  { echo -e "${c_info}[RUN]${c_rst} $*"; }
ok()   { echo -e "${c_ok}[OK] ${c_rst} $*"; }
fail() { echo -e "${c_fail}[FAIL]${c_rst} $*" >&2; }

# -----------------------------------------------------------------------------
# Preconditions
# -----------------------------------------------------------------------------
[ -d "${VEINS_DIR}" ] || { fail "Veins not installed at ${VEINS_DIR}. Run ./scripts/install.sh first."; exit 1; }
[ -d "${SCENARIO_DIR}" ] || { fail "Scenario missing at ${SCENARIO_DIR}."; exit 1; }

# Load env (idempotent)
# shellcheck disable=SC1091
[ -f /etc/profile.d/mirage-omnetpp.sh ] && source /etc/profile.d/mirage-omnetpp.sh
# shellcheck disable=SC1091
[ -f /etc/profile.d/mirage-sumo.sh ]    && source /etc/profile.d/mirage-sumo.sh
export LD_LIBRARY_PATH="${VEINS_DIR}/out/gcc-release/src:${LD_LIBRARY_PATH:-}"

# -----------------------------------------------------------------------------
# Seed-specific route file
# -----------------------------------------------------------------------------
ROU_VARIANT="${SCENARIO_DIR}/highway_seed${SEED}.rou.xml"
ROU_MAIN="${SCENARIO_DIR}/highway.rou.xml"

if [ ! -f "${ROU_VARIANT}" ]; then
    log "Generating per-seed route variants..."
    cd "${SCENARIO_DIR}"
    python3 generate_route_variants.py || {
        fail "generate_route_variants.py failed"; exit 1;
    }
fi

if [ ! -f "${ROU_VARIANT}" ]; then
    fail "Expected ${ROU_VARIANT} after route generation, got nothing"; exit 1
fi

# Snapshot original, swap in the seed variant
BACKUP=""
if [ ! -L "${ROU_MAIN}" ]; then
    BACKUP="${ROU_MAIN}.orig-$$"
    cp "${ROU_MAIN}" "${BACKUP}"
fi
cp "${ROU_VARIANT}" "${ROU_MAIN}"

# -----------------------------------------------------------------------------
# Start launchd
# -----------------------------------------------------------------------------
pkill -f "veins_launchd.*-p ${SUMO_PORT}" 2>/dev/null || true
sleep 1
log "Starting veins_launchd on port ${SUMO_PORT}..."
"${VEINS_DIR}/bin/veins_launchd" -c sumo -p "${SUMO_PORT}" -v \
    > "/tmp/mirage_run_single_launchd_seed${SEED}.log" 2>&1 &
LAUNCHD_PID=$!
sleep 2
if ! kill -0 "${LAUNCHD_PID}" 2>/dev/null; then
    fail "veins_launchd died immediately; see /tmp/mirage_run_single_launchd_seed${SEED}.log"
    exit 1
fi
trap "kill ${LAUNCHD_PID} 2>/dev/null; [ -n '${BACKUP}' ] && mv '${BACKUP}' '${ROU_MAIN}' 2>/dev/null; exit" EXIT INT TERM
ok "launchd PID ${LAUNCHD_PID}"

# -----------------------------------------------------------------------------
# Configurations to run (matches CLAIMS.md)
# -----------------------------------------------------------------------------
CONFIGS=(
    # Baselines (B0..B3, P) + no attack
    B0_Baseline B1_Baseline B2_Baseline B3_Baseline P_Baseline
    # Baselines under A1 (NoStop)
    B0_A1 B1_A1 B2_A1 B3_A1 P_A1
    # Baselines under A2 (WithStop)
    B0_A2 B1_A2 B2_A2 B3_A2 P_A2
    # Ablation: P without EEBL gate
    P_NoGate_Baseline P_NoGate_A1 P_NoGate_A2
)

cd "${SCENARIO_DIR}"
PASS=0; FAIL=0
for cfg in "${CONFIGS[@]}"; do
    log "  ${cfg} (seed ${SEED}) ..."
    LOG="/tmp/mirage_run_single_${cfg}_seed${SEED}.log"
    if timeout 300 ./run -u Cmdenv -c "${cfg}" \
            --sim-time-limit="${SIM_TIME}" \
            --result-dir="results" \
            > "${LOG}" 2>&1; then
        if grep -q "Calling finish()" "${LOG}"; then
            ok "    ${cfg} finished"
            PASS=$((PASS + 1))
        else
            fail "    ${cfg} ended without finish()"
            tail -8 "${LOG}" | sed 's/^/        /' >&2
            FAIL=$((FAIL + 1))
        fi
    else
        fail "    ${cfg} timed out or exited nonzero"
        tail -8 "${LOG}" | sed 's/^/        /' >&2
        FAIL=$((FAIL + 1))
    fi
done

echo ""
echo "================================================================"
echo "  Single-seed run complete"
echo "================================================================"
echo "  Seed:        ${SEED}"
echo "  Configs OK:  ${PASS} / ${#CONFIGS[@]}"
echo "  Configs BAD: ${FAIL} / ${#CONFIGS[@]}"
echo ""
echo "  Next: ./scripts/verify_results.py --seeds ${SEED}"
echo "================================================================"

# Cleanup trap handles launchd kill and route restore
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)

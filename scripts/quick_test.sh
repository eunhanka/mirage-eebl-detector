#!/bin/bash
# =============================================================================
# MIRAGE Artifact: Smoke test
# =============================================================================
# Verifies the install.sh pipeline produced a working simulation environment
# by running a single short experiment (P_A2: MIRAGE vs FakeEEBL_WithStop).
#
# USAGE:
#   ./scripts/quick_test.sh
#
# Takes ~1-2 minutes. Produces a single detlog CSV and checks that MIRAGE
# flagged the attack (suspicious=1 rows present).
#
# Does NOT require sudo. Run as the user who will use the artifact.
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
MIRAGE_PREFIX="${MIRAGE_PREFIX:-/opt/mirage}"
OMNETPP_DIR="${MIRAGE_PREFIX}/omnetpp-5.6.2"
SUMO_PREFIX="${MIRAGE_PREFIX}/sumo-1.8.0"
VEINS_DIR="${MIRAGE_PREFIX}/veins-5.2"
VASP_DIR="${VEINS_DIR}/src/vasp"
SCENARIO_DIR="${VASP_DIR}/scenario"

TEST_CONFIG="P_A2"      # MIRAGE vs A2 (WithStop) attack
SUMO_PORT="${SUMO_PORT:-9999}"
SUMO_LAUNCHD="${VEINS_DIR}/bin/veins_launchd"

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
log()    { echo "[QT]  $*"; }
ok()     { echo "[OK]  $*"; }
warn()   { echo "[WARN] $*" >&2; }
fail()   { echo "[FAIL] $*" >&2; exit 1; }

# -----------------------------------------------------------------------------
# Environment
# -----------------------------------------------------------------------------
setup_env() {
    [ -d "${OMNETPP_DIR}"  ] || fail "OMNeT++ not found at ${OMNETPP_DIR}"
    [ -d "${SUMO_PREFIX}"  ] || fail "SUMO not found at ${SUMO_PREFIX}"
    [ -d "${SCENARIO_DIR}" ] || fail "Scenario dir not found at ${SCENARIO_DIR}"
    [ -x "${SCENARIO_DIR}/run" ] || fail "run script missing at ${SCENARIO_DIR}/run"
    [ -f "${SUMO_LAUNCHD}" ] || fail "sumo-launchd.py missing at ${SUMO_LAUNCHD}"

    export PATH="${OMNETPP_DIR}/bin:${SUMO_PREFIX}/bin:${PATH}"
    export LD_LIBRARY_PATH="${OMNETPP_DIR}/lib:${LD_LIBRARY_PATH:-}"
    export SUMO_HOME="${SUMO_PREFIX}/share/sumo"
    export HOSTNAME="${HOSTNAME:-$(hostname)}"

    command -v opp_run > /dev/null || fail "opp_run not in PATH (check ${OMNETPP_DIR}/bin)"
    command -v sumo    > /dev/null || fail "sumo not in PATH"
    command -v python3 > /dev/null || fail "python3 not in PATH"

    log "Environment OK"
    log "  OMNeT++ : ${OMNETPP_DIR}"
    log "  SUMO    : ${SUMO_PREFIX} (SUMO_HOME=${SUMO_HOME})"
    log "  VEINS   : ${VEINS_DIR}"
}

# -----------------------------------------------------------------------------
# Port / SUMO daemon
# -----------------------------------------------------------------------------
check_port() {
    if command -v lsof > /dev/null; then
        if lsof -i ":${SUMO_PORT}" > /dev/null 2>&1; then
            fail "Port ${SUMO_PORT} is in use. Stop the process or set SUMO_PORT=<other>."
        fi
    elif command -v ss > /dev/null; then
        if ss -tln | grep -q ":${SUMO_PORT} "; then
            fail "Port ${SUMO_PORT} is in use. Stop the process or set SUMO_PORT=<other>."
        fi
    fi
}

SUMO_PID=""

start_sumo() {
    check_port
    log "Starting sumo-launchd on port ${SUMO_PORT}..."
    "${SUMO_LAUNCHD}" -vv -c sumo -p "${SUMO_PORT}" \
        > /tmp/mirage_quick_test_sumo.log 2>&1 &
    SUMO_PID=$!

    # Give it a moment to bind the port
    sleep 2

    if ! kill -0 "${SUMO_PID}" 2>/dev/null; then
        cat /tmp/mirage_quick_test_sumo.log >&2
        fail "sumo-launchd failed to start (see log above)"
    fi
    ok "sumo-launchd started (PID ${SUMO_PID})"
}

stop_sumo() {
    if [ -n "${SUMO_PID}" ] && kill -0 "${SUMO_PID}" 2>/dev/null; then
        log "Stopping sumo-launchd (PID ${SUMO_PID})"
        kill "${SUMO_PID}" 2>/dev/null || true
        wait "${SUMO_PID}" 2>/dev/null || true
    fi
}

# Cleanup on exit (success, failure, or Ctrl+C)
trap stop_sumo EXIT INT TERM

# -----------------------------------------------------------------------------
# Run test config
# -----------------------------------------------------------------------------
run_test() {
    log "Running test configuration: ${TEST_CONFIG}"
    log "  (MIRAGE detector + A2 FakeEEBL_WithStop attack; expected: ~40s)"

    cd "${SCENARIO_DIR}"

    # Mark start so we can identify our detlog afterwards
    local start_time
    start_time=$(date +%s)

    local sim_log=/tmp/mirage_quick_test_run.log
    if ! ./run -u Cmdenv -c "${TEST_CONFIG}" omnetpp.ini > "${sim_log}" 2>&1; then
        log "Simulation failed. Last 40 lines of log:"
        tail -40 "${sim_log}" >&2
        fail "Simulation failed (see ${sim_log})"
    fi

    log "Simulation complete. Log: ${sim_log}"

    # Echo simulation metadata from log
    grep -E "Event|Simulated time|elapsed" "${sim_log}" | tail -5 || true

    # Find the detlog CSV produced by this run (newest matching our start time)
    local latest_csv
    latest_csv=$(find "${SCENARIO_DIR}/results" -maxdepth 1 \
                      -name "detlog-${TEST_CONFIG}-*.csv" \
                      -newermt "@${start_time}" 2>/dev/null \
                 | sort | tail -1)

    if [ -z "${latest_csv}" ] || [ ! -f "${latest_csv}" ]; then
        fail "No detlog CSV produced in ${SCENARIO_DIR}/results/"
    fi

    log "Detection log produced: $(basename "${latest_csv}")"
    log "  Size: $(du -h "${latest_csv}" | cut -f1)"

    LATEST_DETLOG="${latest_csv}"
}

# -----------------------------------------------------------------------------
# Verify detection
# -----------------------------------------------------------------------------
verify_detection() {
    log "Verifying detection output..."

    local total_rows
    total_rows=$(wc -l < "${LATEST_DETLOG}")
    if [ "${total_rows}" -lt 10 ]; then
        fail "Detection log has only ${total_rows} rows; expected hundreds. See ${LATEST_DETLOG}"
    fi
    log "  Total rows: ${total_rows}"

    # Header (first line) should mention the expected columns
    local header
    header=$(head -1 "${LATEST_DETLOG}")
    for col in time hv_id rv_id attack_type det_name suspicious score; do
        if ! echo "${header}" | grep -qw "${col}"; then
            fail "Detection log missing column '${col}' in header: ${header}"
        fi
    done
    log "  Header columns verified"

    # Count suspicious=1 rows (MIRAGE should flag A2 attacks)
    # Column index may vary; find it dynamically.
    local susp_col
    susp_col=$(head -1 "${LATEST_DETLOG}" | tr ',' '\n' | grep -n '^suspicious$' | cut -d: -f1)
    if [ -z "${susp_col}" ]; then
        fail "Could not locate 'suspicious' column"
    fi

    local flagged
    flagged=$(awk -F, -v c="${susp_col}" 'NR>1 && $c==1 {n++} END{print n+0}' "${LATEST_DETLOG}")
    log "  Suspicious rows (flagged by MIRAGE): ${flagged}"

    if [ "${flagged}" -eq 0 ]; then
        fail "MIRAGE flagged 0 rows on an A2 attack config. Expected many. Something is wrong."
    fi

    ok "Detection verified: ${flagged} rows flagged as suspicious"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
echo "================================================================"
echo "  MIRAGE quick_test.sh"
echo "  Configuration: ${TEST_CONFIG} (MIRAGE + A2 WithStop attack)"
echo "================================================================"

setup_env
start_sumo
run_test
verify_detection

echo ""
echo "================================================================"
ok "Quick test PASSED"
echo "================================================================"
echo ""
echo "Next steps:"
echo "  1. Single-seed full run:   cd ${SCENARIO_DIR} && ./run_all.sh"
echo "  2. Multi-seed paper run:   see README.md 'Option B'"

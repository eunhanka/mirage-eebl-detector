#!/bin/bash
# =============================================================================
# MIRAGE Artifact: Installation Script
# =============================================================================
#
# This script installs all dependencies and builds the MIRAGE misbehavior
# detector on top of the VASP / Veins 5.2 / SUMO 1.8.0 / OMNeT++ 5.6.2 stack.
#
# USAGE:
#   sudo ./install.sh [STAGE]
#
# STAGES:
#   deps         - Install apt packages and C++ headers (~2 min)
#   omnetpp      - Build OMNeT++ 5.6.2 from source (~20-40 min)
#   sumo         - Build SUMO 1.8.0 from source (~10-15 min)
#   veins        - Clone Veins 5.2 and VASP at pinned commits (~1 min)
#   mirage       - Overlay MIRAGE sources and build the simulation (~5 min)
#   all          - Run all stages above in order (default)
#
# INSTALLATION LAYOUT (after successful install):
#   /opt/mirage/
#   +-- omnetpp-5.6.2/              <- OMNeT++ build
#   +-- veins-5.2/                  <- Veins + VASP + MIRAGE
#       +-- src/vasp/                   (VASP with MIRAGE overlay)
#   +-- sumo-1.8.0/                 <- SUMO build
#
# REQUIREMENTS:
#   - Ubuntu 20.04 LTS (tested)
#   - sudo / root privileges
#   - ~10 GB free disk space
#   - Internet access (clones from GitHub and eclipse.org)
#
# =============================================================================

set -e                          # Exit on first error
set -u                          # Exit on undefined variable
set -o pipefail                 # Pipe failure = command failure

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
MIRAGE_PREFIX="${MIRAGE_PREFIX:-/opt/mirage}"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "${SCRIPT_DIR}/.." && pwd )"
LIB_DIR="${SCRIPT_DIR}/lib"
LOG_DIR="${MIRAGE_PREFIX}/logs"

# Pinned versions (must match paper's environment)
OMNETPP_VERSION="5.6.2"
SUMO_VERSION="1_8_0"
VEINS_BRANCH="veins-5.2"
VEINS_COMMIT="c5b4d7c4fab0e2b23f78d2e4f90a7ebc512db596"  # tag: veins-5.2
VASP_COMMIT="0ec4af324f3ed729690f1cbd1b1143ebd7f4d6f4"

# Parallel build jobs (fallback: 4 if nproc fails)
MAKE_JOBS="${MAKE_JOBS:-$(nproc 2>/dev/null || echo 4)}"

export MIRAGE_PREFIX SCRIPT_DIR REPO_ROOT LIB_DIR LOG_DIR
export OMNETPP_VERSION SUMO_VERSION VEINS_BRANCH VEINS_COMMIT VASP_COMMIT
export MAKE_JOBS

# -----------------------------------------------------------------------------
# Logging helpers (available to all sub-scripts via export -f)
# -----------------------------------------------------------------------------
log_info()    { echo "[INFO]  $*"; }
log_ok()      { echo "[OK]    $*"; }
log_warn()    { echo "[WARN]  $*" >&2; }
log_error()   { echo "[ERROR] $*" >&2; }
log_stage()   {
    echo ""
    echo "============================================================"
    echo "  STAGE: $*"
    echo "============================================================"
}
export -f log_info log_ok log_warn log_error log_stage

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------
preflight() {
    # Must be root (via sudo)
    if [ "$(id -u)" -ne 0 ]; then
        log_error "This script must be run as root (use: sudo ./install.sh)"
        exit 1
    fi

    # Ubuntu 20.04 check (warn only, not fatal)
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        if [ "${VERSION_ID:-}" != "20.04" ]; then
            log_warn "Tested only on Ubuntu 20.04 LTS; detected: ${PRETTY_NAME:-unknown}"
        fi
    fi

    # lib/ directory must exist
    if [ ! -d "${LIB_DIR}" ]; then
        log_error "Sub-script directory not found: ${LIB_DIR}"
        exit 1
    fi

    # Create install prefix and log dir
    mkdir -p "${MIRAGE_PREFIX}"
    mkdir -p "${LOG_DIR}"
}

# -----------------------------------------------------------------------------
# Stage dispatcher
# -----------------------------------------------------------------------------
run_stage() {
    local stage="$1"
    local script="${LIB_DIR}/${stage}.sh"

    if [ ! -f "${script}" ]; then
        log_error "Unknown stage: ${stage} (no ${script})"
        return 1
    fi

    log_stage "${stage}"
    bash "${script}"
}

usage() {
    cat <<USAGE
Usage: sudo $0 [STAGE]

STAGES:
  deps         Install apt packages and C++ headers
  omnetpp      Build OMNeT++ ${OMNETPP_VERSION} from source
  sumo         Build SUMO ${SUMO_VERSION//_/.} from source
  veins        Clone Veins (${VEINS_BRANCH}) and VASP at pinned commits
  mirage       Overlay MIRAGE and build the simulation
  all          Run all stages above (default)

ENV VARS:
  MIRAGE_PREFIX   Install root (default: /opt/mirage)
  MAKE_JOBS       Parallel build jobs (default: \$(nproc))

EXAMPLES:
  sudo ./install.sh                   # Full install
  sudo ./install.sh all               # Same as above
  sudo ./install.sh deps              # Only apt packages
  sudo MAKE_JOBS=4 ./install.sh all   # Limit parallelism

USAGE
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    local stage="${1:-all}"

    if [ "${stage}" = "-h" ] || [ "${stage}" = "--help" ]; then
        usage
        exit 0
    fi

    preflight

    log_info "MIRAGE artifact installer"
    log_info "  Repository:     ${REPO_ROOT}"
    log_info "  Install prefix: ${MIRAGE_PREFIX}"
    log_info "  Make jobs:      ${MAKE_JOBS}"
    log_info "  Requested stage: ${stage}"

    local start_time
    start_time=$(date +%s)

    case "${stage}" in
        deps)    run_stage "01_deps" ;;
        omnetpp) run_stage "02_omnetpp" ;;
        sumo)    run_stage "03_sumo" ;;
        veins)   run_stage "04_veins" ;;
        mirage)  run_stage "05_mirage" ;;
        all)
            run_stage "01_deps"
            run_stage "02_omnetpp"
            run_stage "03_sumo"
            run_stage "04_veins"
            run_stage "05_mirage"
            ;;
        *)
            log_error "Unknown stage: ${stage}"
            usage
            exit 1
            ;;
    esac

    local end_time elapsed
    end_time=$(date +%s)
    elapsed=$((end_time - start_time))

    echo ""
    echo "============================================================"
    log_ok "Installation complete. Elapsed: ${elapsed}s ($((elapsed / 60))m)"
    echo "============================================================"
    log_info "Next steps:"
    log_info "  1. Verify install:  ./scripts/quick_test.sh"
    log_info "  2. Run experiments: see README.md Section 'Run'"
}

main "$@"

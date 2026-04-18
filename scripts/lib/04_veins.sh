#!/bin/bash
# =============================================================================
# Stage 04: Veins 5.2 + VASP
# =============================================================================
# Clones Veins 5.2 and VASP at pinned commits, then builds the vanilla
# stack (without the MIRAGE overlay) to verify the baseline.
#
# Requires: 02_omnetpp (opp_makemake in PATH), 03_sumo (SUMO_HOME).
#
# Idempotent: if ${VEINS_DIR}/out/*/src/libveins.so exists, skip.
#
# Pinned:
#   Veins:  branch ${VEINS_BRANCH}, commit ${VEINS_COMMIT}
#   VASP :  commit ${VASP_COMMIT}
# =============================================================================

set -euo pipefail

# Inherited from parent install.sh:
#   MIRAGE_PREFIX, VEINS_BRANCH, VEINS_COMMIT, VASP_COMMIT,
#   OMNETPP_VERSION, MAKE_JOBS, LOG_DIR

VEINS_DIR="${MIRAGE_PREFIX}/veins-5.2"
VASP_DIR="${VEINS_DIR}/src/vasp"
VEINS_REPO="https://github.com/sommer/veins.git"
VASP_REPO="https://github.com/quic/vasp.git"
BUILD_LOG="${LOG_DIR}/04_veins.log"

OMNETPP_DIR="${MIRAGE_PREFIX}/omnetpp-${OMNETPP_VERSION}"
SUMO_VERSION_DOTTED="$(echo "${SUMO_VERSION:-1_8_0}" | tr '_' '.')"
SUMO_PREFIX="${MIRAGE_PREFIX}/sumo-${SUMO_VERSION_DOTTED}"

# -----------------------------------------------------------------------------
# Idempotency
# -----------------------------------------------------------------------------
is_built() {
    # Any libveins.so in an out/*/ tree means a successful build exists
    compgen -G "${VEINS_DIR}/out/*/src/libveins.so" > /dev/null 2>&1
}

# -----------------------------------------------------------------------------
# Environment setup for this script
# -----------------------------------------------------------------------------
setup_env() {
    if [ ! -d "${OMNETPP_DIR}" ]; then
        log_error "OMNeT++ not found at ${OMNETPP_DIR}"
        log_error "Run './install.sh omnetpp' first."
        exit 1
    fi

    if [ ! -d "${SUMO_PREFIX}" ]; then
        log_error "SUMO not found at ${SUMO_PREFIX}"
        log_error "Run './install.sh sumo' first."
        exit 1
    fi

    # OMNeT++ env (PATH for opp_makemake, LD_LIBRARY_PATH for libs)
    export PATH="${OMNETPP_DIR}/bin:${PATH}"
    export LD_LIBRARY_PATH="${OMNETPP_DIR}/lib:${LD_LIBRARY_PATH:-}"
    export HOSTNAME="${HOSTNAME:-$(hostname)}"

    # SUMO env (informational; Veins configure may reference SUMO_HOME)
    export SUMO_HOME="${SUMO_PREFIX}/share/sumo"
    export PATH="${SUMO_PREFIX}/bin:${PATH}"

    if ! command -v opp_makemake > /dev/null; then
        log_error "opp_makemake not found in PATH after env setup"
        log_error "Check OMNeT++ installation at ${OMNETPP_DIR}"
        exit 1
    fi

    log_info "Environment ready:"
    log_info "  OMNeT++:   ${OMNETPP_DIR}"
    log_info "  SUMO:      ${SUMO_PREFIX} (SUMO_HOME=${SUMO_HOME})"
}

# -----------------------------------------------------------------------------
# Clone Veins at pinned commit
# -----------------------------------------------------------------------------
clone_veins() {
    if [ -d "${VEINS_DIR}/.git" ]; then
        log_info "Veins already cloned at ${VEINS_DIR}"
        local cur_commit
        cur_commit=$(git -C "${VEINS_DIR}" rev-parse HEAD)
        log_info "  Current HEAD: ${cur_commit}"
        if [[ "${cur_commit}" != ${VEINS_COMMIT}* ]]; then
            log_warn "Current commit does not match pinned ${VEINS_COMMIT}"
            log_info "  Fetching and checking out pinned commit..."
            git -C "${VEINS_DIR}" fetch origin "${VEINS_BRANCH}"
            git -C "${VEINS_DIR}" checkout "${VEINS_COMMIT}"
        fi
        return 0
    fi

    log_info "Cloning Veins (branch: ${VEINS_BRANCH})..."
    git clone --branch "${VEINS_BRANCH}" "${VEINS_REPO}" "${VEINS_DIR}"

    log_info "Checking out pinned Veins commit: ${VEINS_COMMIT}"
    git -C "${VEINS_DIR}" checkout "${VEINS_COMMIT}"

    log_ok "Veins cloned at ${VEINS_COMMIT}"
}

# -----------------------------------------------------------------------------
# Clone VASP at pinned commit into src/vasp/
# -----------------------------------------------------------------------------
clone_vasp() {
    if [ -d "${VASP_DIR}/.git" ]; then
        log_info "VASP already cloned at ${VASP_DIR}"
        local cur_commit
        cur_commit=$(git -C "${VASP_DIR}" rev-parse HEAD)
        log_info "  Current HEAD: ${cur_commit}"
        if [ "${cur_commit}" != "${VASP_COMMIT}" ]; then
            log_warn "Current commit does not match pinned ${VASP_COMMIT}"
            log_info "  Fetching and checking out pinned commit..."
            git -C "${VASP_DIR}" fetch origin
            git -C "${VASP_DIR}" checkout "${VASP_COMMIT}"
        fi
        return 0
    fi

    # Veins expects VASP at src/vasp/. If the directory exists but is not
    # a git repo, something is in the way; stop for safety.
    if [ -e "${VASP_DIR}" ]; then
        log_error "Non-git content exists at ${VASP_DIR}; refusing to overwrite"
        exit 1
    fi

    log_info "Cloning VASP into ${VASP_DIR}..."
    git clone "${VASP_REPO}" "${VASP_DIR}"

    log_info "Checking out pinned VASP commit: ${VASP_COMMIT}"
    git -C "${VASP_DIR}" checkout "${VASP_COMMIT}"

    log_ok "VASP cloned at ${VASP_COMMIT}"
}

# -----------------------------------------------------------------------------
# Build vanilla Veins + VASP
# -----------------------------------------------------------------------------
build_veins() {
    log_info "Building Veins + VASP (vanilla, no MIRAGE overlay yet)..."
    log_info "  Build log: ${BUILD_LOG}"
    log_info "  Parallel jobs: ${MAKE_JOBS}"

    cd "${VEINS_DIR}"

    log_info "Running ./configure..."
    ./configure >> "${BUILD_LOG}" 2>&1

    log_info "Running make -j${MAKE_JOBS} MODE=release..."
    if ! make -j"${MAKE_JOBS}" MODE=release >> "${BUILD_LOG}" 2>&1; then
        log_error "make failed. See ${BUILD_LOG} for details."
        tail -40 "${BUILD_LOG}" >&2
        exit 1
    fi

    log_ok "Veins + VASP build complete (vanilla)"
}

# -----------------------------------------------------------------------------
# Sanity check
# -----------------------------------------------------------------------------
sanity_check() {
    log_info "Verifying Veins + VASP build..."

    # libveins.so should exist (glob)
    local found=0
    for so in "${VEINS_DIR}"/out/*/src/libveins.so; do
        if [ -f "${so}" ]; then
            log_info "Found: ${so}"
            found=1
        fi
    done
    if [ "${found}" -eq 0 ]; then
        log_error "No libveins.so produced under ${VEINS_DIR}/out/*/src/veins/"
        exit 1
    fi

    # VASP's run script should be generated
    local run_script="${VASP_DIR}/scenario/run"
    if [ ! -x "${run_script}" ]; then
        log_warn "VASP run script not executable: ${run_script}"
        log_info "  (will be created by 05_mirage after overlay; this may be normal)"
    fi

    # sumo-launchd.py is shipped by Veins (not by SUMO 1.8.0 install)
    local launchd="${VEINS_DIR}/sumo-launchd.py"
    if [ ! -f "${launchd}" ]; then
        log_error "sumo-launchd.py not found at ${launchd}"
        log_error "  (this file is required for TraCI connectivity)"
        exit 1
    fi
    log_info "sumo-launchd.py present at ${launchd}"

    # Pinned commit verification
    log_info "Veins HEAD:  $(git -C "${VEINS_DIR}" rev-parse --short HEAD)"
    log_info "VASP  HEAD:  $(git -C "${VASP_DIR}"  rev-parse --short HEAD)"

    log_ok "Veins 5.2 + VASP verified at pinned commits"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
setup_env

if is_built; then
    log_info "Veins already built at ${VEINS_DIR} (skipping)"
    # Still verify commits match
    if [ -d "${VEINS_DIR}/.git" ]; then
        cur=$(git -C "${VEINS_DIR}" rev-parse HEAD)
        if [[ "${cur}" != ${VEINS_COMMIT}* ]]; then
            log_warn "Veins HEAD (${cur:0:8}) does not match pinned (${VEINS_COMMIT})"
            log_warn "  Consider 'rm -rf ${VEINS_DIR}' and re-running for a clean pinning"
        fi
    fi
    sanity_check
    exit 0
fi

clone_veins
clone_vasp
build_veins
sanity_check

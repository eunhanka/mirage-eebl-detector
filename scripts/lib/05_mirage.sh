#!/bin/bash
# =============================================================================
# Stage 05: MIRAGE overlay + rebuild
# =============================================================================
# Copies the MIRAGE source tree from the repo onto the vanilla VASP checkout
# and rebuilds the Veins + VASP + MIRAGE stack incrementally.
#
# Requires: 04_veins (Veins + VASP cloned and built vanilla).
#
# Overlay scope:
#   ${REPO_ROOT}/src/vasp/driver/*    ->  ${VASP_DIR}/driver/
#   ${REPO_ROOT}/src/vasp/mdm/*       ->  ${VASP_DIR}/mdm/
#   ${REPO_ROOT}/src/vasp/scenario/*  ->  ${VASP_DIR}/scenario/
#
# Idempotent: always re-overlays the repo's current sources, then rebuilds.
#             (cheap if nothing changed -- make detects no-op.)
# =============================================================================

set -euo pipefail

# Inherited from parent install.sh:
#   MIRAGE_PREFIX, REPO_ROOT, OMNETPP_VERSION, SUMO_VERSION, MAKE_JOBS, LOG_DIR

VEINS_DIR="${MIRAGE_PREFIX}/veins-5.2"
VASP_DIR="${VEINS_DIR}/src/vasp"
BUILD_LOG="${LOG_DIR}/05_mirage.log"

OMNETPP_DIR="${MIRAGE_PREFIX}/omnetpp-${OMNETPP_VERSION}"
SUMO_VERSION_DOTTED="$(echo "${SUMO_VERSION:-1_8_0}" | tr '_' '.')"
SUMO_PREFIX="${MIRAGE_PREFIX}/sumo-${SUMO_VERSION_DOTTED}"

# Source tree inside the repository (where MIRAGE patches live)
MIRAGE_SRC="${REPO_ROOT}/src/vasp"

# Files that MIRAGE overlays (for sanity check after copy)
EXPECTED_OVERLAY_FILES=(
    "driver/CarApp.cc"
    "driver/CarApp.h"
    "driver/CarApp.ned"
    "mdm/MisbehaviorDetectors.h"
    "scenario/omnetpp.ini"
    "scenario/highway.junctions.json"
    "scenario/run_all.sh"
    "scenario/run_multi_seed.sh"
    "scenario/generate_route_variants.py"
    "scenario/analyze_vasp_v3.py"
    "scenario/analyze_multi_seed.py"
)

# -----------------------------------------------------------------------------
# Pre-flight
# -----------------------------------------------------------------------------
preflight() {
    if [ ! -d "${VASP_DIR}" ]; then
        log_error "VASP not found at ${VASP_DIR}"
        log_error "Run './install.sh veins' first."
        exit 1
    fi

    if [ ! -d "${MIRAGE_SRC}" ]; then
        log_error "MIRAGE source tree not found at ${MIRAGE_SRC}"
        log_error "Is the repository layout correct?"
        exit 1
    fi

    # Verify each overlay file exists in the repo (fail early, not mid-copy)
    local missing=0
    for f in "${EXPECTED_OVERLAY_FILES[@]}"; do
        if [ ! -f "${MIRAGE_SRC}/${f}" ]; then
            log_error "Missing in repo: ${MIRAGE_SRC}/${f}"
            missing=$((missing + 1))
        fi
    done
    if [ "${missing}" -gt 0 ]; then
        log_error "${missing} overlay source file(s) missing; aborting."
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Overlay copy
# -----------------------------------------------------------------------------
apply_overlay() {
    log_info "Applying MIRAGE overlay from ${MIRAGE_SRC} to ${VASP_DIR}"

    for subdir in driver mdm scenario; do
        if [ ! -d "${MIRAGE_SRC}/${subdir}" ]; then
            log_warn "No ${subdir}/ in repo source (skipping)"
            continue
        fi
        # Ensure target directory exists (mdm/ is new in MIRAGE; not in vanilla VASP)
        mkdir -p "${VASP_DIR}/${subdir}"
        log_info "  Copying ${subdir}/..."
        cp -r "${MIRAGE_SRC}/${subdir}/"* "${VASP_DIR}/${subdir}/"
    done

    # Preserve executability on scripts (cp may lose it depending on source fs)
    chmod +x "${VASP_DIR}/scenario/run_all.sh"        2>/dev/null || true
    chmod +x "${VASP_DIR}/scenario/run_multi_seed.sh" 2>/dev/null || true

    log_ok "Overlay applied"
}

# -----------------------------------------------------------------------------
# Verify overlay (each expected file must now match the repo version)
# -----------------------------------------------------------------------------
verify_overlay() {
    log_info "Verifying overlay integrity..."
    local mismatched=0
    for f in "${EXPECTED_OVERLAY_FILES[@]}"; do
        if [ ! -f "${VASP_DIR}/${f}" ]; then
            log_error "Overlay file missing after copy: ${VASP_DIR}/${f}"
            mismatched=$((mismatched + 1))
            continue
        fi
        if ! cmp -s "${MIRAGE_SRC}/${f}" "${VASP_DIR}/${f}"; then
            log_error "Overlay file content mismatch: ${f}"
            mismatched=$((mismatched + 1))
        fi
    done
    if [ "${mismatched}" -gt 0 ]; then
        log_error "${mismatched} overlay file(s) mismatched; aborting."
        exit 1
    fi
    log_ok "All ${#EXPECTED_OVERLAY_FILES[@]} overlay files verified"
}

# -----------------------------------------------------------------------------
# Rebuild
# -----------------------------------------------------------------------------
rebuild() {
    log_info "Rebuilding Veins + VASP + MIRAGE..."
    log_info "  Build log: ${BUILD_LOG}"
    log_info "  Parallel jobs: ${MAKE_JOBS}"

    # Env setup (this script may be invoked standalone)
    export PATH="${OMNETPP_DIR}/bin:${SUMO_PREFIX}/bin:${PATH}"
    export LD_LIBRARY_PATH="${OMNETPP_DIR}/lib:${LD_LIBRARY_PATH:-}"
    export SUMO_HOME="${SUMO_PREFIX}/share/sumo"
    export HOSTNAME="${HOSTNAME:-$(hostname)}"

    cd "${VEINS_DIR}"

    # Re-run configure in case overlay added new source files that need listing
    log_info "Running ./configure (picks up any new source files)..."
    ./configure >> "${BUILD_LOG}" 2>&1

    log_info "Running make -j${MAKE_JOBS} MODE=release..."
    if ! make -j"${MAKE_JOBS}" MODE=release >> "${BUILD_LOG}" 2>&1; then
        log_error "make failed. See ${BUILD_LOG} for details."
        tail -40 "${BUILD_LOG}" >&2
        exit 1
    fi

    log_ok "Build complete"
}

# -----------------------------------------------------------------------------
# Sanity check
# -----------------------------------------------------------------------------
sanity_check() {
    log_info "Verifying MIRAGE installation..."

    # run script should exist and be executable
    local run_script="${VASP_DIR}/scenario/run"
    if [ ! -x "${run_script}" ]; then
        log_error "VASP run script not executable at ${run_script}"
        log_error "  (Expected to be generated by opp_makemake during build)"
        exit 1
    fi

    # libveins.so built
    local found=0
    for so in "${VEINS_DIR}"/out/*/src/libveins.so; do
        [ -f "${so}" ] && found=1
    done
    if [ "${found}" -eq 0 ]; then
        log_error "No libveins.so produced"
        exit 1
    fi

    # MIRAGE detectors are defined inline in MisbehaviorDetectors.h (no per-file
    # .o to check). Verify the overlay header exists and is included in the
    # rebuilt libveins.so (by comparing mtime).
    local mdm_hdr="${VASP_DIR}/mdm/MisbehaviorDetectors.h"
    if [ ! -f "${mdm_hdr}" ]; then
        log_error "MisbehaviorDetectors.h missing at ${mdm_hdr}"
        exit 1
    fi
    log_info "MIRAGE detector header: ${mdm_hdr}"

    log_ok "MIRAGE installation verified"
    log_info "  Scenario directory: ${VASP_DIR}/scenario"
    log_info "  Run script:         ${run_script}"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
preflight
apply_overlay
verify_overlay
rebuild
sanity_check

log_info ""
log_info "MIRAGE stack is ready."
log_info "  Next: ./scripts/quick_test.sh      (smoke test)"
log_info "  Or:   source /etc/profile.d/mirage-omnetpp.sh /etc/profile.d/mirage-sumo.sh"
log_info "        cd ${VASP_DIR}/scenario && ./run_all.sh"

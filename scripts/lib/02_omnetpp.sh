#!/bin/bash
# =============================================================================
# Stage 02: OMNeT++ 5.6.2 build from source
# =============================================================================
# Downloads, extracts, and builds OMNeT++ 5.6.2 into ${MIRAGE_PREFIX}.
# Builds take ~20-40 min depending on CPU; ${MAKE_JOBS} parallel jobs.
#
# Requires 01_deps.sh to have run first (bison, flex, qt5, etc.).
#
# Idempotent: if ${OMNETPP_DIR}/bin/opp_run exists, the build is skipped.
#
# VASP-required flag: CXXFLAGS=-std=c++14 must be enabled in configure.user.
# =============================================================================

set -euo pipefail

# Inherited from parent install.sh:
#   MIRAGE_PREFIX, OMNETPP_VERSION, MAKE_JOBS, LOG_DIR

OMNETPP_DIR="${MIRAGE_PREFIX}/omnetpp-${OMNETPP_VERSION}"
TARBALL_URL="https://github.com/omnetpp/omnetpp/releases/download/omnetpp-${OMNETPP_VERSION}/omnetpp-${OMNETPP_VERSION}-src-linux.tgz"
TARBALL_NAME="omnetpp-${OMNETPP_VERSION}-src-linux.tgz"
PROFILE_SCRIPT="/etc/profile.d/mirage-omnetpp.sh"
BUILD_LOG="${LOG_DIR}/02_omnetpp.log"

# -----------------------------------------------------------------------------
# Idempotency check
# -----------------------------------------------------------------------------
is_built() {
    [ -x "${OMNETPP_DIR}/bin/opp_run" ]
}

# -----------------------------------------------------------------------------
# Download and extract
# -----------------------------------------------------------------------------
download_and_extract() {
    if [ -d "${OMNETPP_DIR}" ] && [ -f "${OMNETPP_DIR}/configure.user" ]; then
        log_info "OMNeT++ directory already exists: ${OMNETPP_DIR}"
        log_info "(Use 'rm -rf ${OMNETPP_DIR}' to force a fresh extract)"
        return 0
    fi

    local tarball_path="${MIRAGE_PREFIX}/${TARBALL_NAME}"

    if [ ! -f "${tarball_path}" ]; then
        log_info "Downloading OMNeT++ ${OMNETPP_VERSION} source tarball..."
        log_info "  From: ${TARBALL_URL}"
        curl -fSL --progress-bar -o "${tarball_path}" "${TARBALL_URL}"
        log_ok "Downloaded: ${tarball_path} ($(du -h "${tarball_path}" | cut -f1))"
    else
        log_info "Tarball already downloaded: ${tarball_path}"
    fi

    log_info "Extracting tarball to ${MIRAGE_PREFIX}..."
    tar -xzf "${tarball_path}" -C "${MIRAGE_PREFIX}"

    if [ ! -d "${OMNETPP_DIR}" ]; then
        log_error "Expected directory not found after extraction: ${OMNETPP_DIR}"
        exit 1
    fi

    log_ok "Extracted to ${OMNETPP_DIR}"
}

# -----------------------------------------------------------------------------
# Patch configure.user (enable C++14 as required by VASP)
# -----------------------------------------------------------------------------
patch_configure_user() {
    local cu="${OMNETPP_DIR}/configure.user"
    if [ ! -f "${cu}" ]; then
        log_error "configure.user not found at ${cu}"
        exit 1
    fi

    if grep -qE '^CXXFLAGS=-std=c\+\+14' "${cu}"; then
        log_info "CXXFLAGS=-std=c++14 already enabled in configure.user"
        return 0
    fi

    log_info "Enabling CXXFLAGS=-std=c++14 in configure.user (VASP requirement)..."
    # Try to uncomment an existing commented line first
    sed -i 's|^#\s*CXXFLAGS=-std=c++14|CXXFLAGS=-std=c++14|' "${cu}"

    # If no such line exists (observed with upstream 5.6.2 tarball), append it
    if ! grep -qE '^CXXFLAGS=-std=c\+\+14' "${cu}"; then
        log_info "(No commented line to uncomment; appending to configure.user)"
        echo 'CXXFLAGS=-std=c++14' >> "${cu}"
    fi

    log_ok "configure.user patched"
}

# -----------------------------------------------------------------------------
# Environment setup (replaces OMNeT++'s 'source setenv' which requires a
# login shell and fails in non-interactive/subshell contexts).
# -----------------------------------------------------------------------------
omnetpp_env() {
    export PATH="${OMNETPP_DIR}/bin:${PATH}"
    export LD_LIBRARY_PATH="${OMNETPP_DIR}/lib:${LD_LIBRARY_PATH:-}"
    export HOSTNAME="${HOSTNAME:-$(hostname)}"
}

# -----------------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------------
build_omnetpp() {
    log_info "Building OMNeT++ ${OMNETPP_VERSION} (this takes 20-40 min)..."
    log_info "  Build log: ${BUILD_LOG}"
    log_info "  Parallel jobs: ${MAKE_JOBS}"

    cd "${OMNETPP_DIR}"
    omnetpp_env

    log_info "Running ./configure..."
    if ! ./configure WITH_QTENV=yes WITH_OSG=no WITH_OSGEARTH=no >> "${BUILD_LOG}" 2>&1; then
        log_error "configure failed. See ${BUILD_LOG} for details."
        tail -40 "${BUILD_LOG}" >&2
        exit 1
    fi

    log_info "Running make -j${MAKE_JOBS}..."
    if ! make -j"${MAKE_JOBS}" MODE=release >> "${BUILD_LOG}" 2>&1; then
        log_error "make failed. See ${BUILD_LOG} for details."
        tail -40 "${BUILD_LOG}" >&2
        exit 1
    fi

    log_ok "OMNeT++ build complete"
}

# -----------------------------------------------------------------------------
# Install profile script (persist environment system-wide)
# -----------------------------------------------------------------------------
install_profile() {
    log_info "Installing environment profile at ${PROFILE_SCRIPT}"

    cat > "${PROFILE_SCRIPT}" <<PROFILE
# MIRAGE OMNeT++ environment (installed by mirage-eebl-detector/scripts/install.sh)
export OMNETPP_ROOT="${OMNETPP_DIR}"
export PATH="\${OMNETPP_ROOT}/bin:\${PATH}"
export LD_LIBRARY_PATH="\${OMNETPP_ROOT}/lib:\${LD_LIBRARY_PATH:-}"
export HOSTNAME="\${HOSTNAME:-\$(hostname)}"
PROFILE

    chmod 644 "${PROFILE_SCRIPT}"
    log_ok "Profile script installed; new shells will have OMNeT++ in PATH"
    log_info "  (For current shell: source ${PROFILE_SCRIPT})"
}

# -----------------------------------------------------------------------------
# Sanity check
# -----------------------------------------------------------------------------
sanity_check() {
    log_info "Verifying OMNeT++ installation..."

    local opp_run="${OMNETPP_DIR}/bin/opp_run"
    if [ ! -x "${opp_run}" ]; then
        log_error "opp_run not executable at ${opp_run}"
        exit 1
    fi

    # Need env set for opp_run to find its libs
    omnetpp_env

    local version_output
    version_output=$("${opp_run}" -v 2>&1 | head -3 || true)
    log_info "opp_run version output:"
    echo "${version_output}" | sed 's/^/    /'

    if ! "${opp_run}" -v 2>&1 | grep -qE "5\.6\.2"; then
        log_warn "Version string does not contain '5.6.2' (check output above)"
    fi

    log_ok "OMNeT++ ${OMNETPP_VERSION} verified"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if is_built; then
    log_info "OMNeT++ already built at ${OMNETPP_DIR} (skipping)"
    install_profile
    sanity_check
    exit 0
fi

download_and_extract
patch_configure_user
build_omnetpp
install_profile
sanity_check

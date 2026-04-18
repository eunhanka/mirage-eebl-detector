#!/bin/bash
# =============================================================================
# Stage 03: SUMO 1.8.0 build from source
# =============================================================================
# Downloads, configures, and builds SUMO 1.8.0 into ${MIRAGE_PREFIX}.
# Build time: ~10-15 min with ${MAKE_JOBS} parallel jobs.
#
# Requires 01_deps.sh to have run first (xerces, fox, proj, gdal).
#
# Idempotent: if ${SUMO_PREFIX}/bin/sumo exists, the build is skipped.
#
# Installs:
#   ${SUMO_PREFIX}/bin/sumo, sumo-gui, netedit, netconvert, ...
#   ${SUMO_PREFIX}/share/sumo/tools/sumo-launchd.py (used by Veins)
# =============================================================================

set -euo pipefail

# Inherited from parent install.sh:
#   MIRAGE_PREFIX, SUMO_VERSION, MAKE_JOBS, LOG_DIR

SUMO_TAG="v${SUMO_VERSION}"                            # "v1_8_0"
SUMO_VERSION_DOTTED="${SUMO_VERSION//_/.}"             # "1.8.0"
SUMO_SRC_DIR="${MIRAGE_PREFIX}/sumo-${SUMO_VERSION_DOTTED}-src"
SUMO_BUILD_DIR="${SUMO_SRC_DIR}/build"
SUMO_PREFIX="${MIRAGE_PREFIX}/sumo-${SUMO_VERSION_DOTTED}"
TARBALL_URL="https://github.com/eclipse-sumo/sumo/archive/refs/tags/${SUMO_TAG}.tar.gz"
TARBALL_NAME="sumo-${SUMO_TAG}.tar.gz"
PROFILE_SCRIPT="/etc/profile.d/mirage-sumo.sh"
BUILD_LOG="${LOG_DIR}/03_sumo.log"

# -----------------------------------------------------------------------------
# Idempotency check
# -----------------------------------------------------------------------------
is_built() {
    [ -x "${SUMO_PREFIX}/bin/sumo" ] && \
    [ -f "${SUMO_PREFIX}/share/sumo/tools/sumo-launchd.py" ]
}

# -----------------------------------------------------------------------------
# Download and extract
# -----------------------------------------------------------------------------
download_and_extract() {
    if [ -d "${SUMO_SRC_DIR}" ]; then
        log_info "SUMO source directory already exists: ${SUMO_SRC_DIR}"
        return 0
    fi

    local tarball_path="${MIRAGE_PREFIX}/${TARBALL_NAME}"

    if [ ! -f "${tarball_path}" ]; then
        log_info "Downloading SUMO ${SUMO_VERSION_DOTTED} source tarball..."
        log_info "  From: ${TARBALL_URL}"
        curl -fSL --progress-bar -o "${tarball_path}" "${TARBALL_URL}"
        log_ok "Downloaded: ${tarball_path} ($(du -h "${tarball_path}" | cut -f1))"
    else
        log_info "Tarball already downloaded: ${tarball_path}"
    fi

    log_info "Extracting tarball..."
    tar -xzf "${tarball_path}" -C "${MIRAGE_PREFIX}"

    # GitHub extracts to sumo-<tag-without-v>/. Rename to our convention.
    local extracted="${MIRAGE_PREFIX}/sumo-${SUMO_VERSION}"
    if [ -d "${extracted}" ] && [ ! -d "${SUMO_SRC_DIR}" ]; then
        mv "${extracted}" "${SUMO_SRC_DIR}"
    fi

    if [ ! -d "${SUMO_SRC_DIR}" ]; then
        log_error "Expected source directory not found after extraction: ${SUMO_SRC_DIR}"
        log_info "Directory listing of ${MIRAGE_PREFIX}:"
        ls -la "${MIRAGE_PREFIX}"
        exit 1
    fi

    log_ok "Extracted to ${SUMO_SRC_DIR}"
}

# -----------------------------------------------------------------------------
# Build (out-of-source CMake)
# -----------------------------------------------------------------------------
build_sumo() {
    log_info "Building SUMO ${SUMO_VERSION_DOTTED} (this takes 10-15 min)..."
    log_info "  Build log: ${BUILD_LOG}"
    log_info "  Parallel jobs: ${MAKE_JOBS}"
    log_info "  Install prefix: ${SUMO_PREFIX}"

    mkdir -p "${SUMO_BUILD_DIR}"
    cd "${SUMO_BUILD_DIR}"

    log_info "Running cmake..."
    cmake \
        -DCMAKE_INSTALL_PREFIX="${SUMO_PREFIX}" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCHECK_OPTIONAL_LIBS=OFF \
        .. >> "${BUILD_LOG}" 2>&1

    log_info "Running make -j${MAKE_JOBS}..."
    if ! make -j"${MAKE_JOBS}" >> "${BUILD_LOG}" 2>&1; then
        log_error "make failed. See ${BUILD_LOG} for details."
        tail -30 "${BUILD_LOG}" >&2
        exit 1
    fi

    log_info "Running make install..."
    if ! make install >> "${BUILD_LOG}" 2>&1; then
        log_error "make install failed. See ${BUILD_LOG} for details."
        tail -30 "${BUILD_LOG}" >&2
        exit 1
    fi

    log_ok "SUMO build and install complete"
}

# -----------------------------------------------------------------------------
# Install profile script
# -----------------------------------------------------------------------------
install_profile() {
    log_info "Installing environment profile at ${PROFILE_SCRIPT}"

    cat > "${PROFILE_SCRIPT}" <<PROFILE
# MIRAGE SUMO environment (installed by mirage-eebl-detector/scripts/install.sh)
export SUMO_HOME="${SUMO_PREFIX}/share/sumo"
export PATH="${SUMO_PREFIX}/bin:\${PATH}"
PROFILE

    chmod 644 "${PROFILE_SCRIPT}"
    log_ok "Profile script installed; new shells will have SUMO_HOME set"
    log_info "  (For current shell: source ${PROFILE_SCRIPT})"
}

# -----------------------------------------------------------------------------
# Sanity check
# -----------------------------------------------------------------------------
sanity_check() {
    log_info "Verifying SUMO installation..."

    local sumo_bin="${SUMO_PREFIX}/bin/sumo"

    if [ ! -x "${sumo_bin}" ]; then
        log_error "sumo binary not executable at ${sumo_bin}"
        exit 1
    fi

    log_info "sumo --version:"
    "${sumo_bin}" --version 2>&1 | head -3 | sed 's/^/    /'

    # Confirm version
    if ! "${sumo_bin}" --version 2>&1 | grep -qE "${SUMO_VERSION_DOTTED}"; then
        log_warn "Version string does not contain '${SUMO_VERSION_DOTTED}' (check output above)"
    fi

    log_ok "SUMO ${SUMO_VERSION_DOTTED} verified"
    log_info "  SUMO_HOME: ${SUMO_PREFIX}/share/sumo"
    log_info "  (sumo-launchd.py is provided by Veins; verified in stage 04_veins)"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if is_built; then
    log_info "SUMO already built at ${SUMO_PREFIX} (skipping)"
    install_profile
    sanity_check
    exit 0
fi

download_and_extract
build_sumo
install_profile
sanity_check

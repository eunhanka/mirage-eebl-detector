#!/bin/bash
# =============================================================================
# Stage 01: Dependencies
# =============================================================================
# Installs apt packages, pip packages, and C++ headers required by
# OMNeT++ 5.6.2, SUMO 1.8.0, Veins 5.2, VASP, and MIRAGE.
#
# Idempotent: safe to re-run; already-installed packages are skipped by apt.
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# apt packages
# -----------------------------------------------------------------------------
APT_PACKAGES=(
    # Core build tools
    build-essential
    gcc-9
    g++-9
    make
    cmake
    pkg-config
    git
    curl
    wget
    unzip

    # OMNeT++ 5.6.2 dependencies
    bison
    flex
    perl
    python3
    python3-pip
    python3-dev
    qt5-default
    libqt5opengl5-dev
    libxml2-dev
    zlib1g-dev
    doxygen
    graphviz
    libwebkit2gtk-4.0-37
    libopenscenegraph-dev

    # SUMO 1.8.0 build dependencies
    libxerces-c-dev
    libfox-1.6-dev
    libgdal-dev
    libproj-dev
    libgl2ps-dev
    swig

    # General
    ca-certificates
    gnupg
    lsb-release
)

PIP_PACKAGES=(
    numpy
    pandas
    matplotlib
    scikit-learn
)

# External headers (as required by VASP README)
CSVWRITER_URL="https://raw.githubusercontent.com/al-eax/CSVWriter/cee5f9d0ec72120404c1510708ba818307a6ab80/include/CSVWriter.h"
JSON_URL="https://github.com/nlohmann/json/releases/download/v3.10.5/json.hpp"

INCLUDE_DIR="/usr/include"

# -----------------------------------------------------------------------------
# Bootstrap: install minimal tools (curl, ca-certs) before anything else.
# The base ubuntu:20.04 image does not ship with curl, so we install it via
# apt before the full package list. This also exercises apt connectivity.
# -----------------------------------------------------------------------------
bootstrap_tools() {
    log_info "Bootstrapping minimal tools (apt update + curl + ca-certificates)..."
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl ca-certificates
    log_ok "Bootstrap complete"
}

# -----------------------------------------------------------------------------
# Network check (requires curl, so must run after bootstrap_tools)
# -----------------------------------------------------------------------------
check_network() {
    if ! curl -fsSL --connect-timeout 10 -o /dev/null https://github.com; then
        log_error "Network check failed: cannot reach github.com"
        log_error "This stage requires internet access."
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# apt packages installation
# -----------------------------------------------------------------------------
install_apt() {
    log_info "Installing ${#APT_PACKAGES[@]} apt packages..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        "${APT_PACKAGES[@]}"

    log_ok "apt packages installed"
}

# -----------------------------------------------------------------------------
# pip packages installation
# -----------------------------------------------------------------------------
install_pip() {
    log_info "Installing Python packages: ${PIP_PACKAGES[*]}"
    pip3 install --upgrade pip
    pip3 install "${PIP_PACKAGES[@]}"
    log_ok "pip packages installed"
}

# -----------------------------------------------------------------------------
# C++ headers (CSVWriter.h, json.h)
# -----------------------------------------------------------------------------
install_headers() {
    if [ -f "${INCLUDE_DIR}/CSVWriter.h" ]; then
        log_info "CSVWriter.h already present at ${INCLUDE_DIR}/CSVWriter.h, skipping"
    else
        log_info "Downloading CSVWriter.h..."
        curl -fsSL -o "${INCLUDE_DIR}/CSVWriter.h" "${CSVWRITER_URL}"
        log_ok "CSVWriter.h installed at ${INCLUDE_DIR}/CSVWriter.h"
    fi

    if [ -f "${INCLUDE_DIR}/json.h" ]; then
        log_info "json.h already present at ${INCLUDE_DIR}/json.h, skipping"
    else
        log_info "Downloading json.hpp (v3.10.5) and installing as json.h..."
        # VASP README: download json.hpp and rename to json.h
        curl -fsSL -o "${INCLUDE_DIR}/json.h" "${JSON_URL}"
        log_ok "json.h installed at ${INCLUDE_DIR}/json.h"
    fi
}

# -----------------------------------------------------------------------------
# Sanity check
# -----------------------------------------------------------------------------
sanity_check() {
    log_info "Verifying installations..."
    local failed=0

    for cmd in gcc g++ make cmake git curl python3 pip3 bison flex doxygen swig; do
        if ! command -v "${cmd}" > /dev/null; then
            log_error "Missing command: ${cmd}"
            failed=1
        fi
    done

    for header in "${INCLUDE_DIR}/CSVWriter.h" "${INCLUDE_DIR}/json.h"; do
        if [ ! -f "${header}" ]; then
            log_error "Missing header: ${header}"
            failed=1
        fi
    done

    # Verify Python imports
    if ! python3 -c "import numpy, pandas, matplotlib, sklearn" 2>/dev/null; then
        log_error "Python package import failed"
        python3 -c "import numpy, pandas, matplotlib, sklearn"  # show error
        failed=1
    fi

    if [ "${failed}" -eq 1 ]; then
        log_error "Sanity check failed"
        exit 1
    fi

    log_ok "All dependencies verified"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
bootstrap_tools
check_network
install_apt
install_pip
install_headers
sanity_check

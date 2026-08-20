#!/usr/bin/env bash

set -euo pipefail

DEFAULT_VERSION="1.27.0"
GO_ARCH="linux-amd64"
GO_INSTALL_DIR="/usr/local/go"
PROFILE_FILE="$HOME/.profile"

# Use argument if provided, otherwise use default
GO_VERSION="${1:-$DEFAULT_VERSION}"

GO_ARCHIVE="go${GO_VERSION}.${GO_ARCH}.tar.gz"
GO_URL="https://go.dev/dl/${GO_ARCHIVE}"

echo "======================================"
echo "      Interactive Go Installer"
echo "======================================"
echo
echo "Go version: ${GO_VERSION}"
echo "Architecture: ${GO_ARCH}"
echo "Install location: ${GO_INSTALL_DIR}"
echo

read -rp "Continue? [y/N] " answer

if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi


echo
echo "[1/6] Checking dependencies..."

for cmd in wget tar; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Installing missing dependency: $cmd"
        sudo apt update
        sudo apt install -y "$cmd"
    fi
done


echo
echo "[2/6] Downloading Go ${GO_VERSION}..."

cd /tmp

if [[ -f "$GO_ARCHIVE" ]]; then
    read -rp "${GO_ARCHIVE} already exists. Use it? [Y/n] " answer

    if [[ "$answer" =~ ^[Nn]$ ]]; then
        rm "$GO_ARCHIVE"
        wget "$GO_URL"
    fi
else
    wget "$GO_URL"
fi


echo
echo "[3/6] Removing previous Go installation..."

if [[ -d "$GO_INSTALL_DIR" ]]; then
    echo "Existing installation detected:"
    echo "$GO_INSTALL_DIR"

    read -rp "Remove it before installing Go ${GO_VERSION}? [Y/n] " answer

    if [[ "$answer" =~ ^[Nn]$ ]]; then
        echo "Cancelled."
        exit 1
    fi

    sudo rm -rf "$GO_INSTALL_DIR"
fi


echo
echo "[4/6] Extracting Go..."

sudo tar -C /usr/local -xzf "$GO_ARCHIVE"


echo
echo "[5/6] Configuring PATH..."

PATH_ENTRIES=(
    'export PATH=$PATH:/usr/local/go/bin'
    'export PATH="$PATH:$(go env GOPATH)/bin"'
)

for entry in "${PATH_ENTRIES[@]}"; do
    if ! grep -Fq "$entry" "$PROFILE_FILE" 2>/dev/null; then
        echo "$entry" >> "$PROFILE_FILE"
        echo "Added: $entry"
    fi
done


echo
echo "[6/6] Reloading environment..."

# shellcheck disable=SC1090
source "$PROFILE_FILE"


echo
echo "======================================"
echo "Installation finished"
echo "======================================"

if command -v go >/dev/null 2>&1; then
    go version
else
    echo "Go installed successfully."
    echo "Restart your terminal and run:"
    echo
    echo "  go version"
fi
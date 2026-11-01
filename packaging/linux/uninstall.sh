#!/usr/bin/env sh
set -eu

INSTALL_ROOT="${HOME}/.local/share/shao-lv"
BIN_ROOT="${HOME}/.local/bin"

rm -f "${BIN_ROOT}/shao-lv" "${BIN_ROOT}/music-converter"
rm -f "${HOME}/.local/share/applications/shao-lv.desktop"
rm -rf "${INSTALL_ROOT}"

echo "ShaoLv application files removed. Existing Agent Skills were left unchanged."


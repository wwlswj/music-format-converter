#!/usr/bin/env sh
set -eu

PACKAGE_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
INSTALL_ROOT="${HOME}/.local/share/shao-lv"
BIN_ROOT="${HOME}/.local/bin"
APPLICATIONS="${HOME}/.local/share/applications"

mkdir -p "${INSTALL_ROOT}" "${BIN_ROOT}" "${APPLICATIONS}"
cp -R "${PACKAGE_ROOT}/app/." "${INSTALL_ROOT}/"
chmod +x "${INSTALL_ROOT}/shao-lv" "${INSTALL_ROOT}/music-converter"
ln -sf "${INSTALL_ROOT}/shao-lv" "${BIN_ROOT}/shao-lv"
ln -sf "${INSTALL_ROOT}/music-converter" "${BIN_ROOT}/music-converter"
cp "${PACKAGE_ROOT}/install-skill-"*.sh "${INSTALL_ROOT}/"

cat > "${APPLICATIONS}/shao-lv.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ShaoLv Music Converter
Comment=Batch music and NCM converter
Exec=${BIN_ROOT}/shao-lv
Icon=${INSTALL_ROOT}/_internal/assets/icon.png
Terminal=false
Categories=AudioVideo;Audio;
EOF

echo "ShaoLv installed to ${INSTALL_ROOT}"
echo "Run: ${BIN_ROOT}/shao-lv"
echo "Optional skill installers are in ${INSTALL_ROOT}/install-skill-*.sh"


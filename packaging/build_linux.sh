#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${SHAOLV_VERSION:-0.2.0}"
BUILD_ROOT="${PROJECT_ROOT}/build/linux"
DIST_ROOT="${PROJECT_ROOT}/dist/linux"
ARTIFACT_ROOT="${PROJECT_ROOT}/artifacts"
PACKAGE_NAME="shao-lv-music-converter-${VERSION}-linux-x86_64"
STAGING="${BUILD_ROOT}/${PACKAGE_NAME}"

case "${BUILD_ROOT}" in
  "${PROJECT_ROOT}"/build/*) ;;
  *) echo "Unsafe build path: ${BUILD_ROOT}" >&2; exit 2 ;;
esac
rm -rf "${BUILD_ROOT}" "${DIST_ROOT}"
mkdir -p "${BUILD_ROOT}" "${DIST_ROOT}" "${ARTIFACT_ROOT}" "${STAGING}/app"

python "${PROJECT_ROOT}/packaging/make_icon.py"
python -m PyInstaller \
  --noconfirm --clean --windowed --onedir --name shao-lv \
  --paths "${PROJECT_ROOT}/src" \
  --add-data "${PROJECT_ROOT}/assets:assets" \
  --add-data "${PROJECT_ROOT}/skills:skills" \
  --add-data "${PROJECT_ROOT}/licenses:licenses" \
  --add-data "${PROJECT_ROOT}/README.md:." \
  --add-data "${PROJECT_ROOT}/LICENSE:." \
  --add-data "${PROJECT_ROOT}/THIRD_PARTY_NOTICES.md:." \
  --hidden-import mutagen.monkeysaudio \
  --workpath "${BUILD_ROOT}" --specpath "${BUILD_ROOT}" \
  --distpath "${DIST_ROOT}/gui" \
  "${PROJECT_ROOT}/packaging/entry_gui.py"

python -m PyInstaller \
  --noconfirm --clean --console --onedir --name music-converter \
  --contents-directory music-converter-internal \
  --paths "${PROJECT_ROOT}/src" \
  --add-data "${PROJECT_ROOT}/skills:skills" \
  --add-data "${PROJECT_ROOT}/licenses:licenses" \
  --add-data "${PROJECT_ROOT}/README.md:." \
  --add-data "${PROJECT_ROOT}/LICENSE:." \
  --add-data "${PROJECT_ROOT}/THIRD_PARTY_NOTICES.md:." \
  --hidden-import mutagen.monkeysaudio \
  --workpath "${BUILD_ROOT}/cli-work" --specpath "${BUILD_ROOT}" \
  --distpath "${DIST_ROOT}/cli" \
  "${PROJECT_ROOT}/packaging/entry_cli.py"

cp -a "${DIST_ROOT}/gui/shao-lv/." "${STAGING}/app/"
cp -a "${DIST_ROOT}/cli/music-converter/." "${STAGING}/app/"
chmod +x "${STAGING}/app/shao-lv" "${STAGING}/app/music-converter"
cp -a "${PROJECT_ROOT}/skills" "${STAGING}/skills"
cp -a "${PROJECT_ROOT}/licenses" "${STAGING}/licenses"
cp "${PROJECT_ROOT}/packaging/linux/install.sh" "${STAGING}/install.sh"
cp "${PROJECT_ROOT}/packaging/linux/uninstall.sh" "${STAGING}/uninstall.sh"
cp "${PROJECT_ROOT}/packaging/skill-installers/"*.sh "${STAGING}/"
cp "${PROJECT_ROOT}/README.md" "${PROJECT_ROOT}/LICENSE" "${PROJECT_ROOT}/THIRD_PARTY_NOTICES.md" "${STAGING}/"
chmod +x "${STAGING}"/*.sh

tar -C "${BUILD_ROOT}" -czf "${ARTIFACT_ROOT}/${PACKAGE_NAME}.tar.gz" "${PACKAGE_NAME}"
sha256sum "${ARTIFACT_ROOT}/${PACKAGE_NAME}.tar.gz" > "${ARTIFACT_ROOT}/${PACKAGE_NAME}.tar.gz.sha256"


# Third-party notices

This project uses and distributes the following third-party components. Their own licenses remain in effect.

| Component | Version | Purpose | License / source |
|---|---:|---|---|
| PySide6 | 6.12.0 | Qt widgets and desktop UI | LGPLv3/GPLv3/commercial, https://pypi.org/project/PySide6/ |
| FFmpeg | 9.0.2 essentials build | Audio conversion and probing | GPLv3 build from https://www.gyan.dev/ffmpeg/builds/ |
| Monkey's Audio `MAC.exe` | 13.45 | APE encoding | 3-Clause BSD, https://www.monkeysaudio.com/ |
| Mutagen | 1.48.1 | Audio metadata and cover art | GPL-2.0-or-later, https://mutagen.readthedocs.io/ |
| PyCryptodome | 4.2.0 | AES and fast XOR operations | Public domain/BSD, https://www.pycryptodome.org/ |
| HTTPX | 0.28.1 | LRCLIB HTTP client | BSD-3-Clause, https://www.python-httpx.org/ |
| RapidFuzz | 3.14.6 | Lyrics match scoring | MIT, https://github.com/rapidfuzz/RapidFuzz |
| Pillow | 13.0.0 | Cover image validation and dimensions | HPND, https://python-pillow.org/ |
| Noto Sans SC / Noto Serif SC | Google Fonts variable builds | Bundled Chinese UI typography | SIL Open Font License 1.1, https://fonts.google.com/noto |
| ncmdump-py | 1.1.6 | NCM format reference; adapted under MIT | https://github.com/ww-rm/ncmdump-py |
| LRCLIB | API service | Online lyrics matching | https://lrclib.net/docs |
| PyInstaller | 6.22.3 | Windows/Linux binary packaging | GPL-2.0-or-later with bootloader exception, https://pyinstaller.org/ |
| Inno Setup | 6.7.3 | Windows installer build tool | Inno Setup License, https://jrsoftware.org/isinfo.php |

## Bundled binary hashes

| File | SHA-256 |
|---|---|
| `tools/ffmpeg/bin/ffmpeg.exe` | `3256173F3F8BFFD7DF12227C68ADF68025EDB1832273A9530688A7BB1ED8EDEC` |
| `tools/ffmpeg/bin/ffprobe.exe` | `F0D36ECBBDD3BCFAC3EFA078C96C7271C2E68B3810595552AC3B7F17E9A65C52` |
| `tools/monkeys-audio/MAC.exe` | `A38CD3312DE3ADD27EE6E3482DF12AF47F07757F3BE6429E6406A64D6916D8E7` |
| `assets/fonts/NotoSansSC-Variable.ttf` | `A3041811A78C361B1DE50F953C805E0244951C21C5BD412F7232EF0D899AF0DA` |
| `assets/fonts/NotoSerifSC-Variable.ttf` | `050080D9255A86808F2945BFFAC582B31EF32BC36411CE29563B4961670C66F9` |

The complete FFmpeg license is stored at `tools/ffmpeg/LICENSE`. The Monkey's Audio license is stored at `tools/monkeys-audio/License.txt`. Font licenses are stored under `assets/fonts/`. The PyInstaller license is stored at `licenses/PyInstaller-COPYING.txt`, and the Inno Setup build-tool license at `packaging/windows/InnoSetup-LICENSE.txt`.


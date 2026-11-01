---
name: music-format-converter
description: Batch-convert local audio and NetEase NCM files, normalize artist-title names, optionally create artist/genre/album folders, and resolve LRC lyrics. Use when the user asks to convert, rename, organize, extract, or batch-process music files with this project.
---

# Music Format Converter

Use this skill to operate the local Music Format Converter without opening the GUI. The converter is Windows-first and keeps all audio processing on the local machine.

## Required checks

1. Run `python scripts/run_cli.py doctor --json`.
2. Confirm FFmpeg and FFprobe are ready. Require `ape_output_ready` before offering APE output.
3. Inspect only the source files or directories explicitly named by the user. Do not scan unrelated folders.
4. Confirm the output directory and collision behavior before a real batch when either is ambiguous.

Set `MUSIC_CONVERTER_HOME` to the project root only when automatic discovery fails.

## Conversion workflow

Build a dry-run first when the batch is large or the destination may contain existing files:

```powershell
python scripts/run_cli.py convert SOURCE... --output OUTPUT --format mp3 --bitrate 320 --group-by artist --dry-run --json
```

Then run the requested conversion:

```powershell
python scripts/run_cli.py convert SOURCE... --output OUTPUT --format mp3 --bitrate 320 --json
```

Read the final `event: summary` JSON object. Report successful, skipped, failed, and cancelled counts, output paths, unresolved lyrics, and warnings. Do not claim success for a failed item.

## Defaults

- Target format: MP3.
- Bitrate: 320 kbps for lossy formats.
- Naming: `{artist} - {title}`.
- Folder organization: none; all files go directly under the selected output root.
- Collision policy: add `(2)`, `(3)`, and so on; never silently overwrite.
- Lyrics: use embedded and local lyrics first, then LRCLIB with a conservative confidence threshold.
- A same-basename `.lrc` beside the source file is always preferred over online matching, including when online lookup is disabled.

Use `--no-lyrics` only when requested. Use `--allow-unsynced` only when the user accepts LRC files without reliable timestamps.

## Safety and truthfulness

- Process only files the user states they lawfully possess. Never download music or paid NCM content.
- Do not use a shell string to assemble paths. Let the wrapper pass an argument list to the CLI.
- NCM, MP3, FLAC, WAV, APE, M4A, AAC, OGG, Opus, WMA, and AIFF are audio inputs. NCM metadata and embedded cover art are extracted locally.
- Only track metadata is sent to LRCLIB when lyrics are enabled; audio is never uploaded.
- Lyrics cannot be guaranteed for every track. Keep low-confidence matches pending and never invent lyrics or timestamps.
- Instrumental tracks do not receive an empty LRC file.

## References

- Read [references/format-support.md](references/format-support.md) before explaining bitrate, APE, or output compatibility.
- Read [references/lyrics-policy.md](references/lyrics-policy.md) when resolving ambiguous lyrics or pure-music status.
- Read [references/troubleshooting.md](references/troubleshooting.md) when `doctor` or a conversion fails.


# Troubleshooting

## Doctor reports missing tools

Run:

```powershell
python scripts/run_cli.py doctor --json
```

The project-local executables should exist at:

- `tools/ffmpeg/bin/ffmpeg.exe`
- `tools/ffmpeg/bin/ffprobe.exe`
- `tools/monkeys-audio/MAC.exe`

Do not install or replace tools without user authorization.

## NCM cannot be parsed

Check the error type:

- Header mismatch: the file is not a supported NCM or is corrupted.
- Truncated field: the container size fields exceed the available file.
- Crypto failure: key or metadata encryption data is malformed.
- Post-decrypt probe failure: the decrypted stream is unplayable; do not retry as if it were a valid source.

## Lyrics are pending or absent

Pending means the confidence threshold was not met. Present the candidates and ask the user to choose or provide an LRC. Instrumental tracks intentionally have no LRC.

## Output collision

The default policy renames to `(2)`, `(3)`, and so on. Use `--overwrite skip` or `--overwrite replace` only with clear user intent.


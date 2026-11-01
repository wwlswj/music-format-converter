# Format support and bitrate semantics

## Audio inputs

Supported source extensions:

- `.ncm`
- `.mp3`
- `.flac`
- `.wav`
- `.ape`
- `.m4a`
- `.aac`
- `.ogg`
- `.opus`
- `.wma`
- `.aiff` / `.aif`
- `.alac`

FFprobe remains the authority: an extension alone does not prove the audio stream is readable.

## Audio outputs

- MP3: `libmp3lame`, honors target bitrate.
- FLAC: lossless, ignores bitrate.
- WAV: 24-bit PCM, ignores bitrate.
- M4A: AAC, honors target bitrate.
- ALAC: lossless M4A, ignores bitrate.
- OGG: Vorbis quality selected from the requested target bitrate; the resulting VBR bitrate can vary.
- Opus: honors target bitrate when valid for the channel count; mono output may be capped at 256 kbps.
- WMA: `wmav2`, honors target bitrate when the local FFmpeg build provides the encoder.
- AIFF: 24-bit big-endian PCM, ignores bitrate.
- APE: requires the official Monkey's Audio `MAC.exe`; ignores bitrate.

Use `doctor --json` for the authoritative capability list.

## NCM

NCM decryption is local and bounded. The parser validates header lengths, decrypts audio in chunks, and requires FFprobe to recognize the result before transcoding. Never emit an unverified decrypted file as successful output.


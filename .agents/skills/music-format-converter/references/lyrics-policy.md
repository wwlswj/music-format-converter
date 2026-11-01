# Lyrics policy

Resolution order:

1. NCM metadata lyrics.
2. Lyrics embedded in the source audio.
3. A case-insensitive sibling `.lrc` file with the same file stem. This local lookup remains active even when online lookup is disabled.
4. LRCLIB exact signature and search.

The automatic online match must be conservative. A match is accepted only when normalized title, artist, album, and duration scores exceed the resolver threshold. Ambiguous matches remain pending for human review.

Rules:

- Send only title, artist, album, and duration to LRCLIB.
- Never upload the audio.
- Never fabricate lyrics.
- Never invent timestamps.
- Do not attach a placeholder lyric file to instrumental tracks.
- Plain lyrics are saved only when `--allow-unsynced` is explicitly used; the resulting LRC is marked unsynced.
- Preserve an existing local or embedded timed LRC over online results.


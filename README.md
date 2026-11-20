# sermon-core

The shared part of two church sermon sites: download a church's YouTube
recordings, transcribe them, and load them as sermons with timestamped
paragraphs, Bible references, and series. Each site adds its own output on
top: a static archive or a database export.

Code only. Transcripts, metadata, and each church's series rules stay in the
site that uses them.

## Interface

```python
import sermon_core as sc

sc.ingest(source, limit=None, min_minutes=15)  # discover + download + transcribe new videos
sc.heal(source, limit=None, dry_run=False)     # retranscribe ones that look truncated
corpus = sc.load(source)                       # Corpus(sermons oldest first, skipped with reasons)
groups = sc.group_series(corpus.sermons, rules)  # ordered rules -> MessageSeries
refs = sc.extract_references("Romans 828")     # [Romans 8:28], validated against chapter counts
for m in sc.find_references(text): ...         # spans + Reference, for marking text up in place
```

`source` is anything with the attributes in `sermon_core.Source`: `name`,
`youtube_channel`, `metadata_path`, `transcripts_dir`, `whisper_bin`,
`whisper_model`. Each site loads it from its own YAML.

- **State is the filesystem.** A video is done when `<transcripts_dir>/<id>.txt`
  exists, so `ingest` is resumable and re-running only does what's missing.
  Metadata is cached in `metadata_path` (a live stream cached without a
  duration is refetched once it has ended).
- **Transcription** is Parakeet TDT 0.6B v3 on MLX (Apple silicon), checked by
  a words-per-minute yield gate. whisper.cpp with `-mc 0` is an optional
  fallback; when it isn't installed, a failing transcript is kept and marked
  `low_yield` for `heal` to revisit.
- **References** come from titles (high precision) and transcripts. Speech-to-
  text errors are repaired against each book's chapter count: "Romans 828" is
  8:28, "Jude 24" is 1:24, and "Romans 124" (1:24 or 12:4) is dropped.
- **Series rules** are ordered dicts (`slug`, `title`, `category`, `pattern`,
  `exclude`, `start`/`end` as YYYYMMDD, `book`, `include_ids`, `current`); the
  first match wins. A `book` rule needs the title's book, or an explicit
  "turn to <book> chapter" in the transcript.

## Install

```bash
uv add "sermon-core @ git+https://github.com/lawwu/sermon-core@v0.1.0"
uv add "sermon-core[ingest] @ git+https://github.com/lawwu/sermon-core@v0.1.0"  # to transcribe
```

## Develop

```bash
uv sync
uv run pytest
```

The `ingest` extra (yt-dlp, parakeet-mlx) is only needed to transcribe; the
tests don't use it.

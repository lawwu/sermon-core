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

## Sermon records (schema v1)

Each site used to keep its own idea of a recording: yt-dlp's raw fields, a
curated YAML file, ad-hoc speaker and duplicate handling. A **sermon record**
is the one shape both can produce and check: one record per recording,
described by [`schema/sermon-record.v1.json`](schema/sermon-record.v1.json)
(JSON Schema 2020-12) and mirrored by the dataclasses in
`sermon_core.record`.

```python
from sermon_core import SermonRecord, validate_record
from sermon_core.record import from_ytdlp, from_berean_yaml

errors = validate_record(data)          # [] when valid, else readable messages
record = SermonRecord.from_dict(data)   # raises RecordError if invalid
record.title, record.series, record.passages, record.visible  # curated wins over generated
```

```bash
uv run sermon-record validate records.json more/*.yaml   # exit 1 if any is invalid
```

The fields fall into layers by who owns them:

| Layer | Fields | Owner |
|---|---|---|
| identity | `schema_version`, `id`, `church`, `platform` (youtube, vimeo), `url` | set once |
| `source` | `title`, `upload_date` (ISO date), `duration_s`, `thumbnail`, `chapters` | yt-dlp; tools refresh it, people never edit it |
| `transcript` | `path`, `format` (`whisper` segment lines), `engine` (parakeet_v3, wcpp_mc0, low_yield, failed), `transcribed_at` | the transcriber |
| `curated` | `title`, `speaker`, `series`, `passages`, `summary`, `published`, `duplicate_of` | people; tools never overwrite it |
| `generated` | `kind` (sunday, bible_study, event, other), `series`, `passages`, `verses` | tools; rewritten on every run |

A curated value that is absent or null means "not curated", so a site falls
back to `generated`, then `source`. Unknown fields fail validation at every
level, so a misspelled curated field is caught rather than silently ignored.
Passages and verse refs must each be one Bible reference with a real book and
chapter; the JSON Schema checks their shape and `validate_record` checks the
rest.

The Berean site's `content/recordings/<id>.yaml` maps on mechanically:
`title` and `date` move under `source`, `curated` and `generated` carry over
as they are (`from_berean_yaml` does it). A church with only yt-dlp metadata
gets a record with `source` alone (`from_ytdlp`).

**Versioning.** `schema_version` is `MAJOR.MINOR`. Within a major version
changes are additive only: new optional fields or new enum values, never a
rename, removal, or tightened rule, so a 1.0 record stays valid under every
1.x. A reader refuses a newer minor than it knows (upgrade sermon-core) and
any other major. A breaking change is a new file, `sermon-record.v2.json`,
alongside v1.

## Install

```bash
uv add "sermon-core @ git+https://github.com/lawwu/sermon-core@v0.2.1"
uv add "sermon-core[ingest] @ git+https://github.com/lawwu/sermon-core@v0.2.1"  # to transcribe
```

## Develop

```bash
uv sync
uv run pytest
```

The `ingest` extra (yt-dlp, parakeet-mlx) is only needed to transcribe; the
tests don't use it.

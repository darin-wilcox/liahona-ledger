# liahona-ledger

A command-line tool for ward clerks: enter each week's sacrament meeting
details **once**, then generate the bishopric agenda, the printable program
(as a PDF), and the announcements email from that single source of truth —
using your ward's actual Word templates. Everything is also searchable —
"when did Brother Diaz last speak?", "when did we last sing hymn 169?",
"what's the current campout announcement say?"

## What it does

1. **Collects** meeting details: presiding/conducting, chorister/organist/
   pianist, hymns, prayers, speakers (or testimonies, for Fast Sunday), a
   musical number, ward business (move-ins, releases, callings &
   sustainings with set-apart status, baby blessings, confirmations,
   baptisms), a spiritual thought for the program cover, and announcements.
2. **Generates**, from that one data set, using your ward's real templates:
   - `agenda.docx` — the bishopric's working copy (full sacrament prayers,
     conducting notes, etc.)
   - `program.pdf` — the printed congregation program (also keeps the `.docx`)
   - `announcements.md` — a plain/markdown draft ready to paste into an email
     Both the agenda and the program automatically switch between the regular
     Sunday layout and the Fast & Testimony layout based on the meeting type.
3. **Searches** across every past meeting on file.

Announcements are stored separately from any one Sunday, with a start/expiration
date range and three independent flags (agenda / program / email) — so a
campout announcement can run for three weeks on the program and in email,
while a one-week reminder appears only on the agenda, without re-typing
anything.

## Install

Requires Python 3.10+, [Poetry](https://python-poetry.org/), and
[LibreOffice](https://www.libreoffice.org/) (for the docx → PDF conversion
step only — everything else works without it).

```bash
cd liahona-ledger
poetry install
poetry run liahona-ledger --help
```

Every command below assumes you're running it via `poetry run liahona-ledger ...`
(or `poetry shell` once, then just `liahona-ledger ...` for the rest of the
session). This project is Poetry-managed end to end: dependencies live in
`pyproject.toml`/`poetry.lock`, and `poetry run pytest` runs the test suite.

The app stores its data in a SQLite database at
`~/.liahona-ledger/liahona_ledger.db` (override anytime with the global
`--db /path/to/file.db` option — handy for keeping a test database separate
from your real one, or for storing the db in a synced folder).

## One-time setup

```bash
poetry run liahona-ledger config set \
  --ward-name "Centerville 1st Ward" \
  --output-dir "~/Documents/liahona-ledger-output"

poetry run liahona-ledger config show
```

(`ward-address`/`ward-phone` are accepted too but aren't used by the current
templates, since that information already lives in the program's "Ward
Leadership & General Information" table, which the app doesn't touch.)

## Weekly workflow

Walk through everything interactively (recommended — prompts for every
field, re-editing an existing date keeps prior values as defaults, and it
asks meeting type up front so it can skip the speaker section for Fast Sunday):

```bash
poetry run liahona-ledger meeting wizard next   # "next" = next upcoming Sunday
# or an explicit date:
poetry run liahona-ledger meeting wizard 2026-07-19
```

Or set fields non-interactively (handy for scripting or fixing one thing):

```bash
poetry run liahona-ledger meeting set 2026-07-19 \
  --presiding "Bishop Jenkins" --conducting "Brother McIntyre" \
  --chorister "Sister Lee" --organist "Brother Young" --pianist "Sister Park" \
  --opening-hymn-number 19 --opening-hymn-title "We Thank Thee, O God, for a Prophet" \
  --sacrament-hymn-number 169 --sacrament-hymn-title "As Now We Take the Sacrament" \
  --closing-hymn-number 30 --closing-hymn-title "Come, Come, Ye Saints" \
  --notes "Confirm mic check with Brother Young before 8:45." \
  --spiritual-thought "Charity never faileth" --spiritual-thought-author "Moroni 7:46"

poetry run liahona-ledger speaker add 2026-07-19 --name "Emma Carter" --topic "FHE" --youth
poetry run liahona-ledger speaker add 2026-07-19 --name "Sister Carter" --topic "Faith"
poetry run liahona-ledger speaker add 2026-07-19 --name "Brother Nguyen" --topic "Service"

poetry run liahona-ledger music add 2026-07-19 --performer "Ward Choir" --title "How Firm a Foundation"

poetry run liahona-ledger business add 2026-07-19 --category move_in --person "The Johnson Family"
poetry run liahona-ledger business add 2026-07-19 --category release --person "Brother Lee" \
  --description "Sunday School Teacher"
poetry run liahona-ledger business add 2026-07-19 --category calling_sustaining --person "Brother Diaz" \
  --description "Elders Quorum 2nd Counselor" --set-apart
poetry run liahona-ledger business add 2026-07-19 --category baby_blessing --person "Baby Wilson"
```

For a Fast & Testimony Sunday, just set `--type fast_and_testimony`; the app
automatically switches to the Fast Sunday agenda/program (Bearing of
Testimonies instead of speakers) and skips the speaker slots entirely.

Add a standing announcement (shows up automatically on every meeting whose
date falls in its range):

```bash
poetry run liahona-ledger announcement add \
  --text "Ward campout is August 14-15 at Cherry Hill; sign up in the foyer." \
  --start 2026-07-19 --expires 2026-08-09

# agenda-only reminder, skip the printed program:
poetry run liahona-ledger announcement add \
  --text "Tithing settlement appointments open next week." \
  --start 2026-07-19 --expires 2026-07-26 --no-program
```

Check everything looks right, then generate:

```bash
poetry run liahona-ledger meeting show 2026-07-19
poetry run liahona-ledger generate all 2026-07-19
# or individually:
poetry run liahona-ledger generate agenda 2026-07-19
poetry run liahona-ledger generate program 2026-07-19
poetry run liahona-ledger generate email 2026-07-19
```

Files land in your configured `--output-dir` as `2026-07-19-agenda.docx`,
`2026-07-19-program.pdf` (+ `.docx`), and `2026-07-19-announcements.md`.

If more than two non-youth speakers are on file for a date, the CLI prints a
warning (to stderr) when generating, since the templates only have two
speaker slots.

## Searching

```bash
poetry run liahona-ledger search hymn 169                # or a title fragment
poetry run liahona-ledger search speaker Carter
poetry run liahona-ledger search person Young            # any role: presiding, conducting,
                                                          # chorister, organist, pianist, ward business
poetry run liahona-ledger search announcements campout

poetry run liahona-ledger meeting list --limit 10
poetry run liahona-ledger announcement list --all        # include expired
```

## Template notes

The four templates shipped in `liahona_ledger/templates/` are your actual
Word documents, lightly patched in three places where the source had no
token to fill (everything else is exactly as provided):

| File                   | What changed                                                                                                                                                                                                                                                                          |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Both agenda templates  | "Bishop's Business:" was a bare heading with nothing after it -> added a`[BISHOPS_BUSINESS]` line, which the app fills with any baby blessing / confirmation / baptism / other ward-business item (the dedicated tables only cover move-ins, releases, and callings & sustainings). |
| Both program templates | The Opening/Sacrament/Closing Hymn cells were static`#"` scaffolding with nothing to fill -> added `#[..._PAGE] "[..._TITLE]"` tokens in the same cell, same formatting.                                                                                                          |
| Both program templates | "Ward Announcements" had one week's leftover sample copy (the Thursday religion class blurb) -> replaced with`[ANNOUNCEMENTS_BLOCK]`, filled with that week's program-flagged announcements.                                                                                        |

Everything else -- the `[PRESIDING]`, `[CONDUCTING]`, `[CHORISTER]`,
`[ORGANIST]`/`[PIANIST]`, `[YOUTH SPEAKER]`/`[SPEAKER1]`/`[SPEAKER2]` (program)
or `[YOUTH_SPEAKER]`/`[SPEAKER]` x2 (agenda), `[SPECIAL MUSIC]`/
`[SPECIAL_MUSICAL_NUMBER]`, `[DATE]`/`[MEETING_DATE]`, `[SPIRITUAl_THOUGHT]`,
`[AUTHOR]`, and the Move-Ins/Releases/Calling & Sustaining tables -- are
filled exactly as they appear in your originals.

**`[COVER_IMAGE]`** (program only) is intentionally left blank by the app --
picking a weekly cover photo isn't something it automates yet, so add one
manually in Word before or after generating if you'd like one that week.

**Prayers:** neither agenda template has a token for who's saying the
invocation/benediction (both just say "By Invitation"), so although the app
still stores `opening_prayer`/`closing_prayer` (useful for your own records
and for `search person`), that name won't appear on the generated documents
unless you add a token for it in your template.

If your real templates change later (new wording, a restyle, a logo swap),
just replace the files in `liahona_ledger/templates/`, or point the app at a
copy elsewhere with per-type overrides:

```bash
poetry run liahona-ledger config set --agenda-sacrament-template "/path/to/My Agenda.docx"
poetry run liahona-ledger config set --program-fast-and-testimony-template "/path/to/My FT Program.docx"
```

As long as the same bracket tokens appear somewhere in the document, filling
still works -- table cells, headers, and footers are all scanned, and a token
can even be split across Word "runs" (the engine falls back to a
whole-paragraph rebuild in that case).

## Project layout

```
liahona_ledger/
  db.py            SQLite schema + connection handling
  models.py         dataclasses: Meeting, Speaker, MusicalNumber, WardBusinessItem, Announcement
  repository.py     CRUD + search queries
  documents.py      bracket-token filling engine, dynamic table filling, PDF conversion, email draft
  config.py         ward-level JSON settings (~/.liahona-ledger/config.json)
  cli.py            click-based command line interface
  templates/        your real agenda/program templates (sacrament + fast & testimony)
tests/
  test_smoke.py     pytest suite (poetry run pytest)
pyproject.toml       Poetry project + dependency definitions
poetry.lock          locked dependency versions
```

## Where this can go next

- A thin desktop/web UI on top of the same `repository.py` + `documents.py`
  layer (the CLI is already just a thin wrapper over those).
- Direct email sending (SMTP or a Gmail/Outlook connector) instead of a
  draft file to copy/paste.
- Optional cover-image insertion for `[COVER_IMAGE]` (e.g. from a folder of
  seasonal photos, or a config default).
- A `hymn_history` report: hymns not used in N weeks, to help avoid repeats.
- CSV/JSON export and import, for backup or migrating from a spreadsheet.
- Support for stake conference / general conference / ward conference dates
  beyond just tracking them (no templates exist for those yet, so
  `generate agenda`/`generate program` fall back to the regular sacrament
  templates for those meeting types today).

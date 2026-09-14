"""liahona-ledger command line interface.

Run `liahona-ledger --help` (or `python -m liahona_ledger.cli --help`) to
see every command grouped by area: meeting, speaker, music, business,
announcement, generate, search, config.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import click

from .config import Config, DEFAULT_CONFIG_PATH
from .db import Database, DEFAULT_DB_PATH
from .documents import generate_agenda, generate_announcements_email, generate_program
from .models import Announcement, Meeting, MusicalNumber, Speaker, WardBusinessItem
from .repository import MeetingNotFoundError, Repository


def _next_sunday(from_date: dt.date | None = None) -> dt.date:
    """Next upcoming Sunday. If today IS Sunday, returns today (the meeting
    you're most likely still preparing for), matching the 'next' shorthand
    accepted anywhere a MEETING_DATE argument is used."""
    d = from_date or dt.date.today()
    days_ahead = (6 - d.weekday()) % 7  # Sunday = 6
    return d + dt.timedelta(days=days_ahead)


def _resolve_date(meeting_date: str) -> str:
    """Accepts an ISO date or the literal 'next' (next/this Sunday)."""
    if meeting_date.strip().lower() == "next":
        return _next_sunday().isoformat()
    try:
        dt.date.fromisoformat(meeting_date)
    except ValueError:
        raise click.ClickException(
            f"'{meeting_date}' is not a valid date, expected YYYY-MM-DD (or 'next')."
        )
    return meeting_date


class AppContext:
    def __init__(self, db_path: Path):
        self.db = Database(db_path)
        self.repo = Repository(self.db)
        self.config = Config.load()


@click.group()
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path),
              default=DEFAULT_DB_PATH, show_default=True, help="Path to the SQLite database file.")
@click.pass_context
def cli(ctx: click.Context, db_path: Path):
    """liahona-ledger — plan, generate, and search sacrament meetings."""
    ctx.obj = AppContext(db_path)


# ---------------------------------------------------------------------- #
# config
# ---------------------------------------------------------------------- #
@cli.group()
def config():
    """View or update ward-level settings (name, address, output dir, templates)."""


@config.command("show")
@click.pass_obj
def config_show(app: AppContext):
    c = app.config
    for k, v in c.__dict__.items():
        click.echo(f"{k}: {v or '(not set)'}")
    click.echo(f"\nconfig file: {DEFAULT_CONFIG_PATH}")


@config.command("set")
@click.option("--ward-name", default=None)
@click.option("--ward-address", default=None)
@click.option("--ward-phone", default=None)
@click.option("--output-dir", default=None, type=click.Path(file_okay=False, path_type=Path))
@click.option("--agenda-sacrament-template", default=None, type=click.Path(exists=True, dir_okay=False))
@click.option("--agenda-fast-and-testimony-template", default=None, type=click.Path(exists=True, dir_okay=False))
@click.option("--program-sacrament-template", default=None, type=click.Path(exists=True, dir_okay=False))
@click.option("--program-fast-and-testimony-template", default=None, type=click.Path(exists=True, dir_okay=False))
@click.pass_obj
def config_set(app: AppContext, **kwargs):
    c = app.config
    for key, value in kwargs.items():
        if value is not None:
            setattr(c, key, str(value))
    c.save()
    click.echo("Config updated.")


# ---------------------------------------------------------------------- #
# meeting
# ---------------------------------------------------------------------- #
@cli.group()
def meeting():
    """Create, edit, view, list, and delete sacrament meetings."""


@meeting.command("set")
@click.argument("meeting_date")
@click.option("--type", "meeting_type", default="sacrament",
              type=click.Choice(["sacrament", "fast_and_testimony", "stake_conference",
                                  "general_conference", "ward_conference"]))
@click.option("--presiding", default=None)
@click.option("--conducting", default=None)
@click.option("--chorister", default=None)
@click.option("--organist", default=None)
@click.option("--pianist", default=None)
@click.option("--opening-hymn-number", default=None)
@click.option("--opening-hymn-title", default=None)
@click.option("--sacrament-hymn-number", default=None)
@click.option("--sacrament-hymn-title", default=None)
@click.option("--closing-hymn-number", default=None)
@click.option("--closing-hymn-title", default=None)
@click.option("--opening-prayer", default=None)
@click.option("--closing-prayer", default=None)
@click.option("--notes", "presiding_notes", default=None, help="Free-form agenda notes for the bishopric.")
@click.option("--spiritual-thought", default=None, help="Cover-page quote for the printed program.")
@click.option("--spiritual-thought-author", default=None)
@click.pass_obj
def meeting_set(app: AppContext, meeting_date: str, meeting_type: str, **fields):
    """Create or update the core details of a meeting (keeps existing speakers/music/business).

    MEETING_DATE is an ISO date, e.g. 2026-07-19.
    """
    meeting_date = _resolve_date(meeting_date)
    try:
        existing = app.repo.get_meeting(meeting_date)
    except MeetingNotFoundError:
        existing = Meeting(meeting_date=meeting_date, meeting_type=meeting_type)
    for key, value in fields.items():
        if value is not None:
            setattr(existing, key, value)
    existing.meeting_type = meeting_type
    app.repo.upsert_meeting(existing)
    click.echo(f"Saved meeting {meeting_date}.")


@meeting.command("wizard")
@click.argument("meeting_date")
@click.pass_obj
def meeting_wizard(app: AppContext, meeting_date: str):
    """Interactively walk through entering a full meeting (recommended weekly flow)."""
    meeting_date = _resolve_date(meeting_date)
    try:
        m = app.repo.get_meeting(meeting_date)
        click.echo(f"Editing existing meeting for {meeting_date}. Press Enter to keep current value.")
    except MeetingNotFoundError:
        m = Meeting(meeting_date=meeting_date)

    def ask(label, current):
        return click.prompt(label, default=current or "", show_default=bool(current)) or None

    m.meeting_type = click.prompt(
        "Meeting type", type=click.Choice(["sacrament", "fast_and_testimony"]),
        default=m.meeting_type if m.meeting_type in ("sacrament", "fast_and_testimony") else "sacrament",
    )

    m.presiding = ask("Presiding", m.presiding)
    m.conducting = ask("Conducting", m.conducting)
    m.chorister = ask("Chorister", m.chorister)
    m.organist = ask("Organist", m.organist)
    m.pianist = ask("Pianist", m.pianist)
    m.opening_hymn_number = ask("Opening hymn #", m.opening_hymn_number)
    m.opening_hymn_title = ask("Opening hymn title", m.opening_hymn_title)
    m.opening_prayer = ask("Opening prayer", m.opening_prayer)
    m.sacrament_hymn_number = ask("Sacrament hymn #", m.sacrament_hymn_number)
    m.sacrament_hymn_title = ask("Sacrament hymn title", m.sacrament_hymn_title)

    m.speakers = []
    if m.meeting_type == "fast_and_testimony":
        click.echo("Fast & Testimony meeting -- skipping speakers (Bearing of Testimonies).")
    elif click.confirm("Add speakers now?", default=True):
        order = 0
        while click.confirm(f"  Add speaker #{order + 1}?", default=order == 0):
            name = click.prompt("    Name")
            topic = click.prompt("    Topic", default="", show_default=False) or None
            youth = click.confirm("    Youth speaker?", default=False)
            m.speakers.append(Speaker(name=name, topic=topic, is_youth=youth, order_index=order))
            order += 1

    m.musical_numbers = []
    if click.confirm("Add a musical number?", default=False):
        performer = click.prompt("  Performer")
        title = click.prompt("  Title", default="", show_default=False) or None
        special = click.confirm("  Special musical number (vs. congregation hymn slot)?", default=True)
        m.musical_numbers.append(MusicalNumber(
            performer=performer, title=title,
            slot="special_number" if special else "musical_number",
        ))

    m.closing_hymn_number = ask("Closing hymn #", m.closing_hymn_number)
    m.closing_hymn_title = ask("Closing hymn title", m.closing_hymn_title)
    m.closing_prayer = ask("Closing prayer", m.closing_prayer)
    m.presiding_notes = ask("Notes for the bishopric (timing, reminders, etc.)", m.presiding_notes)
    m.spiritual_thought = ask("Spiritual thought for the program cover (optional)", m.spiritual_thought)
    m.spiritual_thought_author = ask("  ...and its author", m.spiritual_thought_author)

    app.repo.upsert_meeting(m)
    click.echo(f"\nSaved meeting {meeting_date}.")


@meeting.command("show")
@click.argument("meeting_date")
@click.pass_obj
def meeting_show(app: AppContext, meeting_date: str):
    """Show everything on file for a given Sunday."""
    try:
        m = app.repo.get_meeting(meeting_date)
    except MeetingNotFoundError as e:
        raise click.ClickException(str(e))
    click.echo(f"Meeting: {m.meeting_date} ({m.meeting_type})")
    click.echo(f"  Presiding: {m.presiding or '-'}   Conducting: {m.conducting or '-'}")
    click.echo(f"  Chorister: {m.chorister or '-'}   Organist: {m.organist or '-'}   Pianist: {m.pianist or '-'}")
    click.echo(f"  Opening hymn: #{m.opening_hymn_number or '?'} {m.opening_hymn_title or ''}")
    click.echo(f"  Opening prayer: {m.opening_prayer or '-'}")
    if m.ward_business:
        click.echo("  Ward business:")
        for wb in m.ward_business:
            click.echo(f"    - [{wb.category}] {wb.person_name} {('- ' + wb.description) if wb.description else ''}")
    click.echo(f"  Sacrament hymn: #{m.sacrament_hymn_number or '?'} {m.sacrament_hymn_title or ''}")
    if m.speakers:
        click.echo("  Speakers:")
        for s in m.speakers:
            tag = " (youth)" if s.is_youth else ""
            click.echo(f"    - {s.name}{tag}: {s.topic or ''}")
    if m.musical_numbers:
        click.echo("  Musical numbers:")
        for mn in m.musical_numbers:
            click.echo(f"    - {mn.performer}: {mn.title or ''} [{mn.slot}]")
    click.echo(f"  Closing hymn: #{m.closing_hymn_number or '?'} {m.closing_hymn_title or ''}")
    click.echo(f"  Closing prayer: {m.closing_prayer or '-'}")
    if m.presiding_notes:
        click.echo(f"  Notes: {m.presiding_notes}")
    if m.spiritual_thought:
        click.echo(f"  Spiritual thought: \u201c{m.spiritual_thought}\u201d \u2014 {m.spiritual_thought_author or ''}")
    if m.announcements:
        click.echo("  Active announcements:")
        for a in m.announcements:
            chans = ",".join(c for c, on in [("agenda", a.include_in_agenda),
                                              ("program", a.include_in_program),
                                              ("email", a.include_in_email)] if on)
            click.echo(f"    - (#{a.id}) {a.text}  [{chans}]")


@meeting.command("list")
@click.option("--limit", default=20, show_default=True)
@click.pass_obj
def meeting_list(app: AppContext, limit: int):
    """List recent meetings, most recent first."""
    meetings = app.repo.list_meetings(limit=limit)
    if not meetings:
        click.echo("No meetings recorded yet.")
        return
    for m in meetings:
        speaker_names = ", ".join(s.name for s in app.repo.get_meeting(m.meeting_date).speakers)
        click.echo(f"{m.meeting_date}  [{m.meeting_type}]  speakers: {speaker_names or '-'}")


@meeting.command("delete")
@click.argument("meeting_date")
@click.confirmation_option(prompt="Are you sure you want to delete this meeting?")
@click.pass_obj
def meeting_delete(app: AppContext, meeting_date: str):
    """Delete a meeting and all its speakers/music/business rows."""
    try:
        app.repo.delete_meeting(meeting_date)
    except MeetingNotFoundError as e:
        raise click.ClickException(str(e))
    click.echo(f"Deleted meeting {meeting_date}.")


# ---------------------------------------------------------------------- #
# speaker / music / business (fine-grained add commands, useful for
# scripting or quick edits without the full wizard)
# ---------------------------------------------------------------------- #
@cli.group()
def speaker():
    """Add or list speakers for a meeting."""


@speaker.command("add")
@click.argument("meeting_date")
@click.option("--name", required=True)
@click.option("--topic", default=None)
@click.option("--youth", is_flag=True, default=False)
@click.pass_obj
def speaker_add(app: AppContext, meeting_date: str, name: str, topic: str, youth: bool):
    m = _get_or_create(app, meeting_date)
    m.speakers.append(Speaker(name=name, topic=topic, is_youth=youth, order_index=len(m.speakers)))
    app.repo.upsert_meeting(m)
    click.echo(f"Added speaker {name} to {meeting_date}.")


@cli.group()
def music():
    """Add musical numbers for a meeting."""


@music.command("add")
@click.argument("meeting_date")
@click.option("--performer", required=True)
@click.option("--title", default=None)
@click.option("--special/--congregation-slot", default=True,
              help="--special for a special musical number, --congregation-slot if it replaces a hymn slot.")
@click.pass_obj
def music_add(app: AppContext, meeting_date: str, performer: str, title: str, special: bool):
    m = _get_or_create(app, meeting_date)
    m.musical_numbers.append(MusicalNumber(
        performer=performer, title=title,
        slot="special_number" if special else "musical_number",
        order_index=len(m.musical_numbers),
    ))
    app.repo.upsert_meeting(m)
    click.echo(f"Added musical number for {performer} to {meeting_date}.")


@cli.group()
def business():
    """Add ward business items (sustainings, releases, callings, blessings, etc.)."""


@business.command("add")
@click.argument("meeting_date")
@click.option("--category", required=True,
              type=click.Choice(["move_in", "release", "calling_sustaining", "baby_blessing",
                                  "confirmation", "baptism", "other"]))
@click.option("--person", "person_name", required=True)
@click.option("--description", default=None,
              help="Released as / Called or sustained as (not used for move_in).")
@click.option("--set-apart", is_flag=True, default=False,
              help="Only meaningful for --category calling_sustaining.")
@click.pass_obj
def business_add(app: AppContext, meeting_date: str, category: str, person_name: str,
                  description: str, set_apart: bool):
    m = _get_or_create(app, meeting_date)
    m.ward_business.append(WardBusinessItem(
        category=category, person_name=person_name, description=description,
        set_apart=set_apart, order_index=len(m.ward_business),
    ))
    app.repo.upsert_meeting(m)
    click.echo(f"Added {category} for {person_name} to {meeting_date}.")


def _get_or_create(app: AppContext, meeting_date: str) -> Meeting:
    meeting_date = _resolve_date(meeting_date)
    try:
        return app.repo.get_meeting(meeting_date)
    except MeetingNotFoundError:
        return Meeting(meeting_date=meeting_date)


# ---------------------------------------------------------------------- #
# announcement
# ---------------------------------------------------------------------- #
@cli.group()
def announcement():
    """Manage announcements that persist across one or more weeks."""


@announcement.command("add")
@click.option("--text", required=True)
@click.option("--start", "start_date", required=True, help="First Sunday to include it, YYYY-MM-DD.")
@click.option("--expires", "expiration_date", required=True, help="Last Sunday to include it, YYYY-MM-DD (inclusive).")
@click.option("--agenda/--no-agenda", default=True)
@click.option("--program/--no-program", default=True)
@click.option("--email/--no-email", default=True)
@click.pass_obj
def announcement_add(app: AppContext, text: str, start_date: str, expiration_date: str,
                      agenda: bool, program: bool, email: bool):
    start_date = _resolve_date(start_date)
    expiration_date = _resolve_date(expiration_date)
    a = Announcement(text=text, start_date=start_date, expiration_date=expiration_date,
                      include_in_agenda=agenda, include_in_program=program, include_in_email=email)
    a = app.repo.add_announcement(a)
    click.echo(f"Added announcement #{a.id}, active {start_date} through {expiration_date}.")


@announcement.command("list")
@click.option("--all", "include_expired", is_flag=True, default=False, help="Include expired announcements too.")
@click.pass_obj
def announcement_list(app: AppContext, include_expired: bool):
    items = app.repo.list_announcements(include_expired=include_expired)
    if not items:
        click.echo("No announcements on file.")
        return
    for a in items:
        chans = ",".join(c for c, on in [("agenda", a.include_in_agenda),
                                          ("program", a.include_in_program),
                                          ("email", a.include_in_email)] if on)
        click.echo(f"#{a.id}  {a.start_date} → {a.expiration_date}  [{chans}]  {a.text}")


@announcement.command("rm")
@click.argument("announcement_id", type=int)
@click.pass_obj
def announcement_rm(app: AppContext, announcement_id: int):
    app.repo.delete_announcement(announcement_id)
    click.echo(f"Deleted announcement #{announcement_id}.")


# ---------------------------------------------------------------------- #
# generate
# ---------------------------------------------------------------------- #
@cli.group()
def generate():
    """Generate the agenda, program, and/or announcements email for a meeting."""


@generate.command("agenda")
@click.argument("meeting_date")
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.pass_obj
def generate_agenda_cmd(app: AppContext, meeting_date: str, output: Path | None):
    m = _load_or_fail(app, meeting_date)
    _warn_if_too_many_speakers(m)
    out_dir = Path(app.config.output_dir)
    output = output or out_dir / f"{meeting_date}-agenda.docx"
    override_attr = f"agenda_{_config_key(m.meeting_type)}_template"
    override = getattr(app.config, override_attr, None)
    template = Path(override) if override else None
    path = generate_agenda(m, output, template_path=template, ward_name=app.config.ward_name)
    click.echo(f"Agenda written to {path}")


@generate.command("program")
@click.argument("meeting_date")
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.option("--docx-only", is_flag=True, default=False, help="Skip PDF conversion.")
@click.pass_obj
def generate_program_cmd(app: AppContext, meeting_date: str, output: Path | None, docx_only: bool):
    m = _load_or_fail(app, meeting_date)
    _warn_if_too_many_speakers(m)
    out_dir = Path(app.config.output_dir)
    output = output or out_dir / f"{meeting_date}-program.pdf"
    override_attr = f"program_{_config_key(m.meeting_type)}_template"
    override = getattr(app.config, override_attr, None)
    template = Path(override) if override else None
    try:
        path = generate_program(m, output, template_path=template, ward_name=app.config.ward_name,
                                 as_pdf=not docx_only)
    except RuntimeError as e:
        raise click.ClickException(str(e))
    click.echo(f"Program written to {path}")


def _config_key(meeting_type: str) -> str:
    return "fast_and_testimony" if meeting_type == "fast_and_testimony" else "sacrament"


def _warn_if_too_many_speakers(m: Meeting) -> None:
    non_youth = [s for s in m.speakers if not s.is_youth]
    if len(non_youth) > 2:
        click.echo(
            f"Warning: {len(non_youth)} non-youth speakers are on file for {m.meeting_date}, "
            "but the template has only two [SPEAKER] slots -- only the first two will appear.",
            err=True,
        )


@generate.command("email")
@click.argument("meeting_date")
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.pass_obj
def generate_email_cmd(app: AppContext, meeting_date: str, output: Path | None):
    m = _load_or_fail(app, meeting_date)
    out_dir = Path(app.config.output_dir)
    output = output or out_dir / f"{meeting_date}-announcements.md"
    path = generate_announcements_email(m, output, ward_name=app.config.ward_name)
    click.echo(f"Announcements email draft written to {path}")
    click.echo("\n--- preview ---")
    click.echo(path.read_text(encoding="utf-8"))


@generate.command("all")
@click.argument("meeting_date")
@click.pass_context
def generate_all_cmd(ctx: click.Context, meeting_date: str):
    """Generate the agenda, program (PDF), and announcements email in one go."""
    ctx.invoke(generate_agenda_cmd, meeting_date=meeting_date, output=None)
    ctx.invoke(generate_program_cmd, meeting_date=meeting_date, output=None, docx_only=False)
    ctx.invoke(generate_email_cmd, meeting_date=meeting_date, output=None)


def _load_or_fail(app: AppContext, meeting_date: str) -> Meeting:
    meeting_date = _resolve_date(meeting_date)
    try:
        return app.repo.get_meeting(meeting_date)
    except MeetingNotFoundError as e:
        raise click.ClickException(str(e))


# ---------------------------------------------------------------------- #
# search
# ---------------------------------------------------------------------- #
@cli.group()
def search():
    """Search past meetings by hymn, speaker, person/role, or announcement text."""


@search.command("hymn")
@click.argument("query")
@click.pass_obj
def search_hymn_cmd(app: AppContext, query: str):
    results = app.repo.search_hymn(query)
    if not results:
        click.echo("No matches.")
        return
    for date, slot, display in results:
        click.echo(f"{date}  [{slot}]  {display}")


@search.command("speaker")
@click.argument("query")
@click.pass_obj
def search_speaker_cmd(app: AppContext, query: str):
    results = app.repo.search_speaker(query)
    if not results:
        click.echo("No matches.")
        return
    for date, s in results:
        tag = " (youth)" if s.is_youth else ""
        click.echo(f"{date}  {s.name}{tag}: {s.topic or ''}")


@search.command("person")
@click.argument("query")
@click.pass_obj
def search_person_cmd(app: AppContext, query: str):
    results = app.repo.search_person(query)
    if not results:
        click.echo("No matches.")
        return
    for date, detail in results:
        click.echo(f"{date}  {detail}")


@search.command("announcements")
@click.argument("query")
@click.pass_obj
def search_announcements_cmd(app: AppContext, query: str):
    results = app.repo.search_announcements(query)
    if not results:
        click.echo("No matches.")
        return
    for a in results:
        click.echo(f"#{a.id}  {a.start_date} → {a.expiration_date}  {a.text}")


def main():
    cli()


if __name__ == "__main__":
    main()

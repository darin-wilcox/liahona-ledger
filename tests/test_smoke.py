"""Minimal smoke tests. Run with: pytest tests/"""
import shutil
import tempfile
from pathlib import Path

import pytest

from liahona_ledger.db import Database
from liahona_ledger.documents import generate_agenda, generate_announcements_email, generate_program
from liahona_ledger.models import Announcement, Meeting, Speaker, WardBusinessItem
from liahona_ledger.repository import MeetingNotFoundError, Repository


@pytest.fixture
def repo():
    tmp = tempfile.mkdtemp()
    db = Database(Path(tmp) / "test.db")
    yield Repository(db)
    db.close()
    shutil.rmtree(tmp, ignore_errors=True)


def test_upsert_and_get_meeting(repo):
    m = Meeting(meeting_date="2026-07-19", presiding="Bishop Smith")
    m.speakers.append(Speaker(name="Sister Carter", topic="Faith"))
    m.ward_business.append(WardBusinessItem(category="baby_blessing", person_name="Baby Wilson"))
    repo.upsert_meeting(m)

    loaded = repo.get_meeting("2026-07-19")
    assert loaded.presiding == "Bishop Smith"
    assert len(loaded.speakers) == 1
    assert loaded.speakers[0].name == "Sister Carter"
    assert len(loaded.ward_business) == 1


def test_update_replaces_children(repo):
    m = Meeting(meeting_date="2026-07-19")
    m.speakers.append(Speaker(name="First Speaker"))
    repo.upsert_meeting(m)

    m2 = repo.get_meeting("2026-07-19")
    m2.speakers = [Speaker(name="Second Speaker")]
    repo.upsert_meeting(m2)

    loaded = repo.get_meeting("2026-07-19")
    assert [s.name for s in loaded.speakers] == ["Second Speaker"]


def test_missing_meeting_raises(repo):
    with pytest.raises(MeetingNotFoundError):
        repo.get_meeting("2099-01-01")


def test_announcement_active_range(repo):
    a = Announcement(text="Campout signup", start_date="2026-07-19", expiration_date="2026-08-09")
    repo.add_announcement(a)
    m = Meeting(meeting_date="2026-07-26")
    repo.upsert_meeting(m)

    active = repo.active_announcements("2026-07-26")
    assert len(active) == 1
    assert repo.active_announcements("2026-09-01") == []


def test_search_hymn_and_speaker(repo):
    m = Meeting(meeting_date="2026-07-19", sacrament_hymn_number="169",
                sacrament_hymn_title="As Now We Take the Sacrament")
    m.speakers.append(Speaker(name="Sister Carter", topic="Faith"))
    repo.upsert_meeting(m)

    assert any("169" in display for _, _, display in repo.search_hymn("169"))
    assert any(s.name == "Sister Carter" for _, s in repo.search_speaker("Carter"))


def test_generate_agenda_and_email(repo, tmp_path):
    m = Meeting(meeting_date="2026-07-19", presiding="Bishop Smith",
                opening_hymn_number="19", opening_hymn_title="We Thank Thee, O God, for a Prophet")
    m.speakers.append(Speaker(name="Sister Carter", topic="Faith"))
    m.speakers.append(Speaker(name="Brother Nguyen", topic="Service"))
    repo.upsert_meeting(m)
    ann = Announcement(text="Campout signup", start_date="2026-07-19", expiration_date="2026-08-09")
    repo.add_announcement(ann)
    full = repo.get_meeting("2026-07-19")

    agenda_path = generate_agenda(full, tmp_path / "agenda.docx", ward_name="Test Ward")
    assert agenda_path.exists()

    email_path = generate_announcements_email(full, tmp_path / "email.md", ward_name="Test Ward")
    text = email_path.read_text()
    assert "Campout signup" in text


def test_multiline_placeholder_produces_line_breaks(repo, tmp_path):
    """Regression test: multiple speakers in the sequential [SPEAKER] slots
    and multiple ward-business rows must not corrupt adjacent formatting."""
    m = Meeting(meeting_date="2026-07-19")
    m.speakers.append(Speaker(name="Sister Carter", topic="Faith"))
    m.speakers.append(Speaker(name="Brother Nguyen", topic="Service"))
    repo.upsert_meeting(m)
    full = repo.get_meeting("2026-07-19")

    agenda_docx = generate_agenda(full, tmp_path / "agenda.docx")
    from docx import Document
    doc = Document(str(agenda_docx))
    texts = [p.text for p in doc.paragraphs]
    assert any("Sister Carter" in t and "Faith" in t for t in texts)
    assert any("Brother Nguyen" in t and "Service" in t for t in texts)
    # No leftover bracket tokens should remain unresolved.
    assert not any("[SPEAKER]" in t for t in texts)


def test_ward_business_tables_filled(repo, tmp_path):
    from docx import Document

    m = Meeting(meeting_date="2026-07-19")
    m.ward_business.append(WardBusinessItem(category="move_in", person_name="The Johnsons"))
    m.ward_business.append(WardBusinessItem(category="release", person_name="Brother Lee",
                                             description="Sunday School Teacher"))
    m.ward_business.append(WardBusinessItem(category="calling_sustaining", person_name="Brother Diaz",
                                             description="Elders Quorum 2nd Counselor", set_apart=True))
    m.ward_business.append(WardBusinessItem(category="baby_blessing", person_name="Baby Wilson"))
    repo.upsert_meeting(m)
    full = repo.get_meeting("2026-07-19")

    agenda_docx = generate_agenda(full, tmp_path / "agenda.docx")
    doc = Document(str(agenda_docx))

    all_cell_text = " | ".join(
        cell.text for table in doc.tables for row in table.rows for cell in row.cells
    )
    assert "The Johnsons" in all_cell_text
    assert "Brother Lee" in all_cell_text and "Sunday School Teacher" in all_cell_text
    assert "Brother Diaz" in all_cell_text and "\u2714" in all_cell_text

    body_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Baby Wilson" in body_text  # routed to Bishop's Business, not a table


def test_fast_and_testimony_uses_different_template(repo, tmp_path):
    from docx import Document

    m = Meeting(meeting_date="2026-08-02", meeting_type="fast_and_testimony", presiding="Bishop Smith")
    repo.upsert_meeting(m)
    full = repo.get_meeting("2026-08-02")

    agenda_docx = generate_agenda(full, tmp_path / "agenda.docx")
    doc = Document(str(agenda_docx))
    body_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Bearing of Testimonies" in body_text
    assert "[SPEAKER]" not in body_text

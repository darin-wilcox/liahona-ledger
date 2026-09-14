"""CRUD + search operations on top of the Database layer.

Everything here speaks in terms of the dataclasses in models.py, so the
CLI (and any future UI) never has to touch raw SQL.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from .db import Database
from .models import Announcement, Meeting, MusicalNumber, Speaker, WardBusinessItem


class MeetingNotFoundError(Exception):
    pass


class Repository:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------ #
    # Meetings
    # ------------------------------------------------------------------ #
    def upsert_meeting(self, m: Meeting) -> Meeting:
        """Create or update a meeting by its (unique) meeting_date.

        Child rows (speakers/musical numbers/ward business) are replaced
        wholesale on update, since a clerk editing a week typically
        re-enters the full slate rather than patching one field.
        """
        with self.db.cursor() as cur:
            cur.execute("SELECT id FROM meetings WHERE meeting_date = ?", (m.meeting_date,))
            row = cur.fetchone()
            fields = dict(
                meeting_date=m.meeting_date,
                meeting_type=m.meeting_type,
                presiding=m.presiding,
                conducting=m.conducting,
                chorister=m.chorister,
                organist=m.organist,
                pianist=m.pianist,
                opening_hymn_number=m.opening_hymn_number,
                opening_hymn_title=m.opening_hymn_title,
                sacrament_hymn_number=m.sacrament_hymn_number,
                sacrament_hymn_title=m.sacrament_hymn_title,
                closing_hymn_number=m.closing_hymn_number,
                closing_hymn_title=m.closing_hymn_title,
                opening_prayer=m.opening_prayer,
                closing_prayer=m.closing_prayer,
                presiding_notes=m.presiding_notes,
                spiritual_thought=m.spiritual_thought,
                spiritual_thought_author=m.spiritual_thought_author,
            )
            if row:
                meeting_id = row["id"]
                set_clause = ", ".join(f"{k} = :{k}" for k in fields)
                cur.execute(
                    f"UPDATE meetings SET {set_clause}, updated_at = datetime('now') "
                    f"WHERE id = :id",
                    {**fields, "id": meeting_id},
                )
                cur.execute("DELETE FROM speakers WHERE meeting_id = ?", (meeting_id,))
                cur.execute("DELETE FROM musical_numbers WHERE meeting_id = ?", (meeting_id,))
                cur.execute("DELETE FROM ward_business WHERE meeting_id = ?", (meeting_id,))
            else:
                cols = ", ".join(fields)
                placeholders = ", ".join(f":{k}" for k in fields)
                cur.execute(f"INSERT INTO meetings ({cols}) VALUES ({placeholders})", fields)
                meeting_id = cur.lastrowid

            for i, s in enumerate(m.speakers):
                cur.execute(
                    "INSERT INTO speakers (meeting_id, order_index, name, topic, is_youth) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (meeting_id, i, s.name, s.topic, int(s.is_youth)),
                )
            for i, mn in enumerate(m.musical_numbers):
                cur.execute(
                    "INSERT INTO musical_numbers (meeting_id, order_index, performer, title, slot) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (meeting_id, i, mn.performer, mn.title, mn.slot),
                )
            for i, wb in enumerate(m.ward_business):
                cur.execute(
                    "INSERT INTO ward_business (meeting_id, order_index, category, person_name, description, set_apart) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (meeting_id, i, wb.category, wb.person_name, wb.description, int(wb.set_apart)),
                )
            m.id = meeting_id
        return m

    def get_meeting(self, meeting_date: str) -> Meeting:
        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM meetings WHERE meeting_date = ?", (meeting_date,))
            row = cur.fetchone()
            if not row:
                raise MeetingNotFoundError(f"No meeting found for {meeting_date}")
            m = self._row_to_meeting(row)

            cur.execute(
                "SELECT * FROM speakers WHERE meeting_id = ? ORDER BY order_index", (m.id,)
            )
            m.speakers = [
                Speaker(id=r["id"], name=r["name"], topic=r["topic"],
                        is_youth=bool(r["is_youth"]), order_index=r["order_index"])
                for r in cur.fetchall()
            ]

            cur.execute(
                "SELECT * FROM musical_numbers WHERE meeting_id = ? ORDER BY order_index", (m.id,)
            )
            m.musical_numbers = [
                MusicalNumber(id=r["id"], performer=r["performer"], title=r["title"],
                               slot=r["slot"], order_index=r["order_index"])
                for r in cur.fetchall()
            ]

            cur.execute(
                "SELECT * FROM ward_business WHERE meeting_id = ? ORDER BY order_index", (m.id,)
            )
            m.ward_business = [
                WardBusinessItem(id=r["id"], category=r["category"], person_name=r["person_name"],
                                  description=r["description"], set_apart=bool(r["set_apart"]),
                                  order_index=r["order_index"])
                for r in cur.fetchall()
            ]

            m.announcements = self.active_announcements(meeting_date)
        return m

    def list_meetings(self, limit: Optional[int] = None) -> list[Meeting]:
        with self.db.cursor() as cur:
            q = "SELECT * FROM meetings ORDER BY meeting_date DESC"
            if limit:
                q += f" LIMIT {int(limit)}"
            cur.execute(q)
            return [self._row_to_meeting(r) for r in cur.fetchall()]

    def delete_meeting(self, meeting_date: str) -> None:
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM meetings WHERE meeting_date = ?", (meeting_date,))
            if cur.rowcount == 0:
                raise MeetingNotFoundError(f"No meeting found for {meeting_date}")

    @staticmethod
    def _row_to_meeting(row: sqlite3.Row) -> Meeting:
        return Meeting(
            id=row["id"],
            meeting_date=row["meeting_date"],
            meeting_type=row["meeting_type"],
            presiding=row["presiding"],
            conducting=row["conducting"],
            chorister=row["chorister"],
            organist=row["organist"],
            pianist=row["pianist"],
            opening_hymn_number=row["opening_hymn_number"],
            opening_hymn_title=row["opening_hymn_title"],
            sacrament_hymn_number=row["sacrament_hymn_number"],
            sacrament_hymn_title=row["sacrament_hymn_title"],
            closing_hymn_number=row["closing_hymn_number"],
            closing_hymn_title=row["closing_hymn_title"],
            opening_prayer=row["opening_prayer"],
            closing_prayer=row["closing_prayer"],
            presiding_notes=row["presiding_notes"],
            spiritual_thought=row["spiritual_thought"],
            spiritual_thought_author=row["spiritual_thought_author"],
        )

    # ------------------------------------------------------------------ #
    # Announcements
    # ------------------------------------------------------------------ #
    def add_announcement(self, a: Announcement) -> Announcement:
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO announcements "
                "(text, start_date, expiration_date, include_in_agenda, include_in_program, include_in_email) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (a.text, a.start_date, a.expiration_date, int(a.include_in_agenda),
                 int(a.include_in_program), int(a.include_in_email)),
            )
            a.id = cur.lastrowid
        return a

    def delete_announcement(self, announcement_id: int) -> None:
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM announcements WHERE id = ?", (announcement_id,))

    def active_announcements(self, meeting_date: str) -> list[Announcement]:
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT * FROM announcements "
                "WHERE start_date <= ? AND expiration_date >= ? "
                "ORDER BY start_date, id",
                (meeting_date, meeting_date),
            )
            return [self._row_to_announcement(r) for r in cur.fetchall()]

    def list_announcements(self, include_expired: bool = False) -> list[Announcement]:
        with self.db.cursor() as cur:
            if include_expired:
                cur.execute("SELECT * FROM announcements ORDER BY start_date DESC")
            else:
                cur.execute(
                    "SELECT * FROM announcements WHERE expiration_date >= date('now') "
                    "ORDER BY start_date"
                )
            return [self._row_to_announcement(r) for r in cur.fetchall()]

    @staticmethod
    def _row_to_announcement(row: sqlite3.Row) -> Announcement:
        return Announcement(
            id=row["id"],
            text=row["text"],
            start_date=row["start_date"],
            expiration_date=row["expiration_date"],
            include_in_agenda=bool(row["include_in_agenda"]),
            include_in_program=bool(row["include_in_program"]),
            include_in_email=bool(row["include_in_email"]),
        )

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
    def search_speaker(self, name_fragment: str) -> list[tuple[str, Speaker]]:
        """Return (meeting_date, Speaker) pairs, most recent first."""
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT m.meeting_date, s.id, s.name, s.topic, s.is_youth, s.order_index "
                "FROM speakers s JOIN meetings m ON m.id = s.meeting_id "
                "WHERE s.name LIKE ? ORDER BY m.meeting_date DESC",
                (f"%{name_fragment}%",),
            )
            return [
                (r["meeting_date"], Speaker(id=r["id"], name=r["name"], topic=r["topic"],
                                             is_youth=bool(r["is_youth"]), order_index=r["order_index"]))
                for r in cur.fetchall()
            ]

    def search_hymn(self, number_or_title: str) -> list[tuple[str, str, str]]:
        """Return (meeting_date, slot, hymn_display) for any hymn slot matching."""
        like = f"%{number_or_title}%"
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT meeting_date, opening_hymn_number, opening_hymn_title, "
                "sacrament_hymn_number, sacrament_hymn_title, closing_hymn_number, closing_hymn_title "
                "FROM meetings "
                "WHERE opening_hymn_number LIKE :l OR opening_hymn_title LIKE :l "
                "   OR sacrament_hymn_number LIKE :l OR sacrament_hymn_title LIKE :l "
                "   OR closing_hymn_number LIKE :l OR closing_hymn_title LIKE :l "
                "ORDER BY meeting_date DESC",
                {"l": like},
            )
            results = []
            for r in cur.fetchall():
                for slot, num, title in (
                    ("opening", r["opening_hymn_number"], r["opening_hymn_title"]),
                    ("sacrament", r["sacrament_hymn_number"], r["sacrament_hymn_title"]),
                    ("closing", r["closing_hymn_number"], r["closing_hymn_title"]),
                ):
                    if num and like.strip("%").lower() in (num or "").lower():
                        results.append((r["meeting_date"], slot, f"#{num} {title or ''}".strip()))
                    elif title and like.strip("%").lower() in (title or "").lower():
                        results.append((r["meeting_date"], slot, f"#{num} {title or ''}".strip()))
            return results

    def search_person(self, name_fragment: str) -> list[tuple[str, str]]:
        """Search across presiding/conducting/chorister/organist/prayers/ward business."""
        like = f"%{name_fragment}%"
        out: list[tuple[str, str]] = []
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT meeting_date, presiding, conducting, chorister, organist, "
                "opening_prayer, closing_prayer FROM meetings "
                "WHERE presiding LIKE :l OR conducting LIKE :l OR chorister LIKE :l "
                "   OR organist LIKE :l OR opening_prayer LIKE :l OR closing_prayer LIKE :l "
                "ORDER BY meeting_date DESC",
                {"l": like},
            )
            for r in cur.fetchall():
                for role in ("presiding", "conducting", "chorister", "organist",
                             "opening_prayer", "closing_prayer"):
                    if r[role] and name_fragment.lower() in r[role].lower():
                        out.append((r["meeting_date"], f"{role}: {r[role]}"))

            cur.execute(
                "SELECT m.meeting_date, wb.category, wb.person_name, wb.description "
                "FROM ward_business wb JOIN meetings m ON m.id = wb.meeting_id "
                "WHERE wb.person_name LIKE ? ORDER BY m.meeting_date DESC",
                (like,),
            )
            for r in cur.fetchall():
                out.append((r["meeting_date"], f"{r['category']}: {r['person_name']} "
                                                f"({r['description'] or ''})".strip()))
        out.sort(key=lambda t: t[0], reverse=True)
        return out

    def search_announcements(self, keyword: str) -> list[Announcement]:
        like = f"%{keyword}%"
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT * FROM announcements WHERE text LIKE ? ORDER BY start_date DESC", (like,)
            )
            return [self._row_to_announcement(r) for r in cur.fetchall()]

"""Dataclasses representing liahona-ledger domain objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Speaker:
    name: str
    topic: Optional[str] = None
    is_youth: bool = False
    order_index: int = 0
    id: Optional[int] = None


@dataclass
class MusicalNumber:
    performer: str
    title: Optional[str] = None
    slot: str = "musical_number"  # musical_number | special_number
    order_index: int = 0
    id: Optional[int] = None


@dataclass
class WardBusinessItem:
    # move_in | release | calling_sustaining | baby_blessing | confirmation | baptism | other
    #   - move_in: just a name (new-member record received)
    #   - release: person_name + description (role released from)
    #   - calling_sustaining: person_name + description (new position) + set_apart
    #   - baby_blessing / confirmation / baptism / other: freeform, listed under
    #     "Bishop's Business" since the template has no dedicated table for these
    category: str
    person_name: str
    description: Optional[str] = None
    set_apart: bool = False
    order_index: int = 0
    id: Optional[int] = None


@dataclass
class Announcement:
    text: str
    start_date: str
    expiration_date: str
    include_in_agenda: bool = True
    include_in_program: bool = True
    include_in_email: bool = True
    id: Optional[int] = None


@dataclass
class Meeting:
    meeting_date: str  # ISO YYYY-MM-DD
    meeting_type: str = "sacrament"
    presiding: Optional[str] = None
    conducting: Optional[str] = None
    chorister: Optional[str] = None
    organist: Optional[str] = None
    pianist: Optional[str] = None
    opening_hymn_number: Optional[str] = None
    opening_hymn_title: Optional[str] = None
    sacrament_hymn_number: Optional[str] = None
    sacrament_hymn_title: Optional[str] = None
    closing_hymn_number: Optional[str] = None
    closing_hymn_title: Optional[str] = None
    opening_prayer: Optional[str] = None
    closing_prayer: Optional[str] = None
    presiding_notes: Optional[str] = None
    spiritual_thought: Optional[str] = None
    spiritual_thought_author: Optional[str] = None
    id: Optional[int] = None

    speakers: list[Speaker] = field(default_factory=list)
    musical_numbers: list[MusicalNumber] = field(default_factory=list)
    ward_business: list[WardBusinessItem] = field(default_factory=list)
    announcements: list[Announcement] = field(default_factory=list)

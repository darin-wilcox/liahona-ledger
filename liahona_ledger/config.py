"""Small JSON config file for ward-level settings (name/address/phone,
default output directory, custom template paths) so the CLI doesn't need
these passed as flags every week."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG_PATH = Path.home() / ".liahona-ledger" / "config.json"


@dataclass
class Config:
    ward_name: str = ""
    ward_address: str = ""
    ward_phone: str = ""
    output_dir: str = str(Path.home() / "liahona-ledger-output")
    # Overrides for the bundled templates -- leave unset to use the ones
    # shipped in liahona_ledger/templates/ (built from the ward's real docs).
    agenda_sacrament_template: Optional[str] = None
    agenda_fast_and_testimony_template: Optional[str] = None
    program_sacrament_template: Optional[str] = None
    program_fast_and_testimony_template: Optional[str] = None

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> "Config":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in data.items() if k in known}
        return cls(**{**asdict(cls()), **data})

    def save(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

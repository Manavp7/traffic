"""Enforcement zones (red-light / speed / no-parking) + automatic challan issuance.

When a violation occurs on a segment covered by a matching enforcement zone, a challan
is auto-issued with signed evidence (the "auto-evidence packaging" workflow).
"""

from __future__ import annotations

from traffic_os.common.logging import get_logger
from traffic_os.enforcement.challan import ChallanService
from traffic_os.schemas import Challan, EnforcementZone, Violation

log = get_logger("enforcement.zones")

# which violation types each zone kind enforces
_ZONE_VIOLATIONS = {
    "red_light": {"red_light"},
    "speed": {"speeding"},
    "no_parking": {"illegal_parking"},
}


class ZoneService:
    def __init__(self, storage, challans: ChallanService | None = None) -> None:
        self.storage = storage
        self.challans = challans or ChallanService(storage)

    def add_zone(self, zone: EnforcementZone) -> EnforcementZone:
        self.storage.db.upsert("enforcement_zone", zone)
        return zone

    def zones(self) -> list[EnforcementZone]:
        return self.storage.db.find("enforcement_zone", EnforcementZone, limit=1000)

    def _zone_map(self) -> dict[str, list[EnforcementZone]]:
        out: dict[str, list[EnforcementZone]] = {}
        for z in self.zones():
            out.setdefault(z.segment_id, []).append(z)
        return out

    def enforce(self, violations: list[Violation]) -> list[Challan]:
        """Auto-issue challans for violations that fall inside a matching zone."""
        zmap = self._zone_map()
        issued: list[Challan] = []
        for v in violations:
            zones = zmap.get(v.segment_id or "", [])
            if any(v.type.value in _ZONE_VIOLATIONS.get(z.kind, set()) for z in zones):
                issued.append(self.challans.issue_for_violation(v))
        log.info("Zone enforcement issued %d challans", len(issued))
        return issued

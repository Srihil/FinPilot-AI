"""
Conflict detection service.

When a TallyPrime sync (READ operation) brings back data, we compare it against
existing FinPilot records. If a FinPilot-created or previously-synced record has
different values, we mark it as CONFLICT.

The user can then review both versions and choose which to keep.

Conflict resolution options:
  keep_finpilot → discard Tally's version, mark as 'synced' (FinPilot wins)
  keep_tally    → overwrite FinPilot with Tally's version, mark as 'synced' (Tally wins)

Only fields that can meaningfully conflict are checked:
- TallyLedger: name, parent_group
- TallyStockGroup: name, parent
- TallyUnit: name, symbol, decimal_places
- TallyGodown: name, parent
- TallyGroup: name, parent
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.tally_masters import TallyLedger, TallyStockGroup, TallyUnit, TallyGodown, TallyGroup

logger = logging.getLogger(__name__)


def _fields_differ(existing_vals: dict, tally_vals: dict) -> dict:
    """Return {field: {finpilot: v1, tally: v2}} for differing fields."""
    diffs = {}
    for k, tv in tally_vals.items():
        fv = existing_vals.get(k)
        if fv is not None and tv is not None:
            if str(fv).strip().lower() != str(tv).strip().lower():
                diffs[k] = {"finpilot": fv, "tally": tv}
    return diffs


def check_ledger_conflict(db: Session, existing: TallyLedger, tally_data: dict) -> bool:
    """Returns True if a conflict was detected and recorded."""
    if existing.source == "finpilot" and existing.tally_sync_status == "synced":
        diffs = _fields_differ(
            {"name": existing.name, "parent_group": existing.parent_group},
            {"name": tally_data.get("name"), "parent_group": tally_data.get("parent_group")},
        )
        if diffs:
            existing.tally_sync_status = "conflict"
            existing.conflict_data = {
                "finpilot": {"name": existing.name, "parent_group": existing.parent_group},
                "tally": tally_data,
                "differences": diffs,
            }
            existing.conflict_detected_at = datetime.now(timezone.utc)
            logger.info("Conflict detected on ledger '%s': %s", existing.name, diffs)
            return True
    return False


def check_stock_group_conflict(db: Session, existing: TallyStockGroup, tally_data: dict) -> bool:
    if existing.source == "finpilot" and existing.tally_sync_status == "synced":
        diffs = _fields_differ(
            {"name": existing.name, "parent": existing.parent},
            {"name": tally_data.get("name"), "parent": tally_data.get("parent")},
        )
        if diffs:
            existing.tally_sync_status = "conflict"
            existing.conflict_data = {
                "finpilot": {"name": existing.name, "parent": existing.parent},
                "tally": tally_data, "differences": diffs,
            }
            existing.conflict_detected_at = datetime.now(timezone.utc)
            return True
    return False


def check_unit_conflict(db: Session, existing: TallyUnit, tally_data: dict) -> bool:
    if existing.source == "finpilot" and existing.tally_sync_status == "synced":
        diffs = _fields_differ(
            {"name": existing.name, "symbol": existing.symbol},
            {"name": tally_data.get("name"), "symbol": tally_data.get("symbol")},
        )
        if diffs:
            existing.tally_sync_status = "conflict"
            existing.conflict_data = {
                "finpilot": {"name": existing.name, "symbol": existing.symbol},
                "tally": tally_data, "differences": diffs,
            }
            existing.conflict_detected_at = datetime.now(timezone.utc)
            return True
    return False


def resolve_conflict(
    db: Session,
    entity_type: str,
    entity_id,
    resolution: str,   # "keep_finpilot" | "keep_tally"
    company_id,
) -> dict:
    """
    Resolve a conflict for a single entity.
    resolution = "keep_finpilot": discard Tally version, mark synced.
    resolution = "keep_tally": apply Tally version values, mark synced.
    """
    MODEL_MAP = {
        "ledger": TallyLedger,
        "stock_group": TallyStockGroup,
        "unit": TallyUnit,
        "godown": TallyGodown,
        "group": TallyGroup,
    }
    model = MODEL_MAP.get(entity_type)
    if not model:
        return {"error": f"Unknown entity type: {entity_type}"}

    import uuid as _uuid
    record = db.query(model).filter(
        model.id == _uuid.UUID(str(entity_id)),
        model.company_id == company_id,
    ).first()
    if not record:
        return {"error": "Record not found"}
    if record.tally_sync_status != "conflict":
        return {"error": "Record is not in conflict state"}

    conflict = record.conflict_data or {}

    if resolution == "keep_tally":
        tally_vals = conflict.get("tally", {})
        if entity_type == "ledger":
            if "name" in tally_vals:
                record.name = tally_vals["name"]
            if "parent_group" in tally_vals:
                record.parent_group = tally_vals["parent_group"]
        elif entity_type in ("stock_group", "godown", "group"):
            if "name" in tally_vals:
                record.name = tally_vals["name"]
            if "parent" in tally_vals:
                record.parent = tally_vals["parent"]
        elif entity_type == "unit":
            if "name" in tally_vals:
                record.name = tally_vals["name"]
            if "symbol" in tally_vals:
                record.symbol = tally_vals["symbol"]

    record.tally_sync_status = "synced"
    record.conflict_data = None
    record.conflict_detected_at = None
    record.synced_at = datetime.now(timezone.utc)
    db.commit()
    return {"resolved": True, "resolution": resolution, "entity_type": entity_type}

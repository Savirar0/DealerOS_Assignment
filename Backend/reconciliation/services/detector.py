"""




Disagreement Detector - Finds discrepancies between System A and System B.

Detects 4 types of disagreements:
1. Missing in B - System A record with no System B entries
2. Orphan in B - System B entry with no matching System A record
3. Duplicate in B - Multiple System B entries for same System A record
4. Value Mismatch - Different total_value vs value for matched pair

Uses Decimal comparison with epsilon (abs_tol=0.01) for value mismatch.
"""
from decimal import Decimal
from math import isclose
from django.db import transaction

from reconciliation.models import (
    SystemARecord,
    SystemBEntry,
    Disagreement,
    Location,
    Organization,
)


# Epsilon for value comparison (1 cent tolerance)
VALUE_EPSILON = Decimal('0.01')


def _json_serializable(val):
    """Convert Decimal to string for JSON serialization."""
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, dict):
        return {k: _json_serializable(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_json_serializable(v) for v in val]
    return val


def values_match(val_a: Decimal | None, val_b: Decimal | None) -> bool:
    """
    Compare two Decimal values with epsilon tolerance.
    
    Returns True if both are None, or if absolute difference <= 0.01
    """
    if val_a is None and val_b is None:
        return True
    if val_a is None or val_b is None:
        return False
    return isclose(val_a, val_b, abs_tol=VALUE_EPSILON)


def detect_missing_in_b() -> list[dict]:
    """
    Rule 1: System A records with NO System B entries pointing to them.
    
    Returns list of disagreement dicts ready for creation.
    """
    disagreements = []
    
    # Get all System A records with their matched System B entries count
    system_a_records = SystemARecord.objects.select_related('location', 'location__org').all()
    
    for record in system_a_records:
        # Count matched System B entries
        b_entries_count = record.system_b_entries.count()
        
        if b_entries_count == 0:
            disagreements.append({
                'system_a_record': record,
                'system_b_entry': None,
                'reason': Disagreement.Reason.MISSING_IN_B,
                'system_a_value': record.total_value,
                'system_b_value': None,
                'location': record.location,
                'org': record.location.org,
                'details': _json_serializable({
                    'record_id': record.record_id,
                    'category_code': record.category_code,
                    'event_date': str(record.event_date),
                    'actor_id': record.actor_id,
                    'state': record.state,
                })
            })
    
    return disagreements


def detect_orphans_in_b() -> list[dict]:
    """
    Rule 2: System B entries with NO matching System A record.
    
    These are entries where matched_record is None.
    """
    disagreements = []
    
    orphan_entries = SystemBEntry.objects.filter(
        matched_record=None
    ).select_related('location', 'location__org')
    
    for entry in orphan_entries:
        disagreements.append({
            'system_a_record': None,
            'system_b_entry': entry,
            'reason': Disagreement.Reason.ORPHAN_IN_B,
            'system_a_value': None,
            'system_b_value': entry.value,
            'location': entry.location,
            'org': entry.location.org if entry.location else None,
            'details': _json_serializable({
                'entry_id': entry.entry_id,
                'record_ref': entry.record_ref,
                'record_ref_clean': entry.record_ref_clean,
                'label': entry.label,
                'recorded_on': str(entry.recorded_on) if entry.recorded_on else None,
                'parse_errors': entry.parse_errors,
            })
        })
    
    return disagreements


def detect_duplicates_in_b() -> list[dict]:
    """
    Rule 3: System A records with MULTIPLE System B entries.
    
    For each System A record with >1 matched System B entry,
    create one disagreement per extra entry (or one for the group).
    We'll create one disagreement per duplicate entry beyond the first.
    """
    disagreements = []
    
    system_a_records = SystemARecord.objects.select_related('location', 'location__org').all()
    
    for record in system_a_records:
        b_entries = list(record.system_b_entries.all())
        
        if len(b_entries) > 1:
            # First entry is "primary", rest are duplicates
            for i, entry in enumerate(b_entries[1:], start=2):
                disagreements.append({
                    'system_a_record': record,
                    'system_b_entry': entry,
                    'reason': Disagreement.Reason.DUPLICATE_IN_B,
                    'system_a_value': record.total_value,
                    'system_b_value': entry.value,
                    'location': record.location,
                    'org': record.location.org,
                    'details': _json_serializable({
                        'record_id': record.record_id,
                        'duplicate_number': i,
                        'total_duplicates': len(b_entries),
                        'primary_entry_id': b_entries[0].entry_id,
                        'primary_entry_value': str(b_entries[0].value) if b_entries[0].value else None,
                    })
                })
    
    return disagreements


def detect_value_mismatches() -> list[dict]:
    """
    Rule 4: Matched pairs where total_value != value (beyond epsilon).
    
    Only checks entries that HAVE a matched_record.
    Skips orphans (handled by Rule 2).
    """
    disagreements = []
    
    # Get all matched entries with their System A record
    matched_entries = SystemBEntry.objects.exclude(
        matched_record=None
    ).select_related(
        'matched_record', 
        'matched_record__location', 
        'matched_record__location__org',
        'location',
        'location__org'
    )
    
    for entry in matched_entries:
        record = entry.matched_record
        
        # Compare values with epsilon
        if not values_match(record.total_value, entry.value):
            disagreements.append({
                'system_a_record': record,
                'system_b_entry': entry,
                'reason': Disagreement.Reason.VALUE_MISMATCH,
                'system_a_value': record.total_value,
                'system_b_value': entry.value,
                'location': record.location,
                'org': record.location.org,
                'details': _json_serializable({
                    'record_id': record.record_id,
                    'entry_id': entry.entry_id,
                    'difference': str(abs(record.total_value - entry.value)) if entry.value else None,
                    'category_code': record.category_code,
                    'record_state': record.state,
                })
            })
    
    return disagreements


def run_all_detections() -> dict:
    """
    Run all 4 detection rules and return combined results.
    
    Does NOT save to database - returns list of disagreement dicts.
    """
    all_disagreements = []
    
    all_disagreements.extend(detect_missing_in_b())
    all_disagreements.extend(detect_orphans_in_b())
    all_disagreements.extend(detect_duplicates_in_b())
    all_disagreements.extend(detect_value_mismatches())
    
    # Count by reason
    reason_counts = {}
    for d in all_disagreements:
        reason = d['reason']
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    
    return {
        'total': len(all_disagreements),
        'by_reason': reason_counts,
        'disagreements': all_disagreements,
    }


@transaction.atomic
def save_disagreements(disagreements: list[dict]) -> dict:
    """
    Save disagreements to database.
    
    Clears existing disagreements first, then bulk creates new ones.
    Returns stats.
    """
    # Clear existing
    deleted_count, _ = Disagreement.objects.all().delete()
    
    # Bulk create
    to_create = []
    for d in disagreements:
        # Skip if org is None (orphan with no location)
        if d['org'] is None:
            continue
            
        to_create.append(Disagreement(
            system_a_record=d['system_a_record'],
            system_b_entry=d['system_b_entry'],
            reason=d['reason'],
            system_a_value=d['system_a_value'],
            system_b_value=d['system_b_value'],
            location=d['location'],
            org=d['org'],
            details=d['details'],
        ))
    
    created = Disagreement.objects.bulk_create(to_create)
    
    return {
        'deleted': deleted_count,
        'created': len(created),
        'skipped': len(disagreements) - len(to_create),
    }


def run_full_detection() -> dict:
    """
    Run complete detection pipeline: detect -> save -> return stats.
    """
    detection_results = run_all_detections()
    save_results = save_disagreements(detection_results['disagreements'])
    
    return {
        **detection_results,
        **save_results,
    }
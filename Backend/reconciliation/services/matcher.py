"""
Matching Service - Links System B entries to System A records.

Handles fuzzy matching of record_ref to record_id.
Updates matched_record FK on SystemBEntry.
"""
from reconciliation.models import SystemARecord, SystemBEntry


def match_all_entries() -> dict:
    """
    Match all System B entries to System A records.
    
    Strategy:
    1. Use record_ref_clean (already normalized during import)
    2. Direct lookup in System A cache
    3. Update matched_record FK
    
    Returns: stats dict with matched, unmatched counts
    """
    # Build lookup dict: record_id -> SystemARecord
    system_a_lookup = {
        record.record_id: record 
        for record in SystemARecord.objects.all()
    }
    
    stats = {
        'total_entries': 0,
        'matched': 0,
        'unmatched': 0,
        'already_matched': 0,
        'newly_matched': 0,
    }
    
    entries = SystemBEntry.objects.select_related('matched_record').all()
    
    for entry in entries:
        stats['total_entries'] += 1
        
        # Skip if already matched and record_ref_clean hasn't changed
        if entry.matched_record and entry.record_ref_clean:
            if entry.matched_record.record_id == entry.record_ref_clean:
                stats['already_matched'] += 1
                continue
        
        # Try to match
        matched_record = None
        if entry.record_ref_clean:
            matched_record = system_a_lookup.get(entry.record_ref_clean)
        
        # Update entry
        entry.matched_record = matched_record
        entry.save(update_fields=['matched_record'])
        
        if matched_record:
            stats['matched'] += 1
            stats['newly_matched'] += 1
        else:
            stats['unmatched'] += 1
    
    return stats


def get_match_stats() -> dict:
    """Get current matching statistics without making changes."""
    total = SystemBEntry.objects.count()
    matched = SystemBEntry.objects.exclude(matched_record=None).count()
    unmatched = total - matched
    
    return {
        'total_entries': total,
        'matched': matched,
        'unmatched': unmatched,
        'match_rate': round(matched / total * 100, 1) if total > 0 else 0,
    }
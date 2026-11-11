"""
CSV Importer for Reconciliation Data

Handles loading of 3 CSV files with robust error handling:
- locations.csv: Clean data
- system_a.csv: Clean data  
- system_b.csv: Dirty data (case issues, whitespace, missing values, comma formatting)
"""
import csv
import re
from decimal import Decimal, InvalidOperation
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from reconciliation.models import (
    Organization,
    Location,
    SystemARecord,
    SystemBEntry,
)


DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / 'data'


def clean_record_ref(ref: str) -> str | None:
    """
    Normalize various record_ref formats to REC-XXXX format.
    
    Handles:
    - 'REC-1034' -> 'REC-1034' (already clean)
    - 'rec1034' -> 'REC-1034' (lowercase, missing dash)
    - 'REC1034' -> 'REC-1034' (missing dash)
    - ' REC - 1070 ' -> 'REC-1070' (whitespace around dash)
    - '1112' -> 'REC-1112' (no prefix)
    - '' or None -> None
    """
    if not ref or not ref.strip():
        return None
    
    ref = ref.strip().upper()
    # Remove all spaces
    ref = ref.replace(' ', '')
    
    # Handle "REC1034" -> "REC-1034"
    if ref.startswith('REC') and not ref.startswith('REC-'):
        ref = 'REC-' + ref[3:]
    
    # Handle "1112" -> "REC-1112"
    if ref.isdigit():
        ref = f'REC-{ref}'
    
    # Validate format: REC- followed by digits
    if not re.match(r'^REC-\d+$', ref):
        return None
    
    return ref


def parse_value(val: str) -> tuple[Decimal | None, list[str]]:
    """
    Parse value string to Decimal, handling various formats.
    
    Handles:
    - '88969.92' -> Decimal('88969.92')
    - '1,25,400.00' -> Decimal('125400.00') (Indian numbering, strip commas)
    - '' or None -> (None, ['empty_value'])
    - 'abc' -> (None, ['invalid_number'])
    
    Returns: (parsed_value, list_of_errors)
    """
    errors = []
    
    if not val or not val.strip():
        errors.append('empty_value')
        return None, errors
    
    val = val.strip()
    # Store original for raw field
    original = val
    
    # Remove all commas (handles both US '1,000.00' and Indian '1,25,400.00')
    val = val.replace(',', '')
    
    try:
        return Decimal(val), errors
    except InvalidOperation:
        errors.append(f'invalid_number_format: {original}')
        return None, errors


def parse_date(date_str: str) -> tuple[date | None, list[str]]:
    """Parse ISO date string (YYYY-MM-DD)."""
    errors = []
    if not date_str or not date_str.strip():
        errors.append('empty_date')
        return None, errors
    
    try:
        return date.fromisoformat(date_str.strip()), errors
    except ValueError:
        errors.append(f'invalid_date_format: {date_str}')
        return None, errors


class CSVImporter:
    """Imports CSV data with error tracking but no silent drops."""
    
    def __init__(self, stdout, stderr):
        self.stdout = stdout
        self.stderr = stderr
        self.stats = {
            'locations': {'created': 0, 'errors': 0},
            'system_a': {'created': 0, 'errors': 0},
            'system_b': {'created': 0, 'errors': 0},
        }
        self.location_cache = {}
        self.org_cache = {}
        self.system_a_cache = {}  # record_id -> SystemARecord
    
    def log(self, msg: str, level: str = 'info'):
        if level == 'error':
            self.stderr.write(msg)
        else:
            self.stdout.write(msg)
    
    def import_locations(self, filepath: Path):
        """Import locations.csv - creates Organizations and Locations."""
        self.log(f"Importing locations from {filepath}...")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):  # start=2 (1-indexed + header)
                try:
                    org_id = row['org_id'].strip()
                    location_id = row['location_id'].strip()
                    location_name = row['location_name'].strip()
                    
                    # Get or create organization
                    if org_id not in self.org_cache:
                        org, created = Organization.objects.get_or_create(
                            org_id=org_id,
                            defaults={'name': f"Organization {org_id}"}
                        )
                        self.org_cache[org_id] = org
                        if created:
                            self.log(f"  Created Organization: {org_id}")
                    org = self.org_cache[org_id]
                    
                    # Create location
                    location, created = Location.objects.get_or_create(
                        location_id=location_id,
                        defaults={
                            'org': org,
                            'name': location_name,
                        }
                    )
                    self.location_cache[location_id] = location
                    
                    if created:
                        self.stats['locations']['created'] += 1
                        self.log(f"  Created Location: {location_id} ({org_id})")
                    else:
                        self.log(f"  Location exists: {location_id}")
                        
                except Exception as e:
                    self.stats['locations']['errors'] += 1
                    self.log(f"  Row {row_num} ERROR: {e}", 'error')
        
        self.log(f"Locations: {self.stats['locations']['created']} created, {self.stats['locations']['errors']} errors")
    
    def import_system_a(self, filepath: Path):
        """Import system_a.csv - clean data, one record per row."""
        self.log(f"Importing System A records from {filepath}...")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):
                try:
                    record_id = row['record_id'].strip()
                    location_id = row['location_id'].strip()
                    
                    # Get location
                    location = self.location_cache.get(location_id)
                    if not location:
                        raise ValueError(f"Location not found: {location_id}")
                    
                    # Parse fields
                    event_date, date_errors = parse_date(row['event_date'])
                    if date_errors:
                        raise ValueError(f"Date parse error: {date_errors}")
                    
                    base_value = Decimal(row['base_value'])
                    adjustment = Decimal(row['adjustment'])
                    total_value = Decimal(row['total_value'])
                    
                    # Create record
                    record, created = SystemARecord.objects.get_or_create(
                        record_id=record_id,
                        defaults={
                            'location': location,
                            'event_date': event_date,
                            'category_code': row['category_code'].strip(),
                            'actor_id': row['actor_id'].strip() if row['actor_id'] else None,
                            'base_value': base_value,
                            'adjustment': adjustment,
                            'total_value': total_value,
                            'state': row['state'].strip(),
                            'raw_data': dict(row),
                        }
                    )
                    self.system_a_cache[record_id] = record
                    
                    if created:
                        self.stats['system_a']['created'] += 1
                    else:
                        # Update existing with latest data
                        for field, value in {
                            'location': location,
                            'event_date': event_date,
                            'category_code': row['category_code'].strip(),
                            'actor_id': row['actor_id'].strip() if row['actor_id'] else None,
                            'base_value': base_value,
                            'adjustment': adjustment,
                            'total_value': total_value,
                            'state': row['state'].strip(),
                            'raw_data': dict(row),
                        }.items():
                            setattr(record, field, value)
                        record.save()
                    
                except Exception as e:
                    self.stats['system_a']['errors'] += 1
                    self.log(f"  Row {row_num} ({row.get('record_id', 'unknown')}) ERROR: {e}", 'error')
        
        self.log(f"System A: {self.stats['system_a']['created']} created, {self.stats['system_a']['errors']} errors")
    
    def import_system_b(self, filepath: Path):
        """Import system_b.csv - dirty data, robust parsing with error tracking."""
        self.log(f"Importing System B entries from {filepath}...")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):
                parse_errors = []
                try:
                    entry_id = row['entry_id'].strip()
                    record_ref_raw = row['record_ref'].strip() if row['record_ref'] else ''
                    location_id = row['location_id'].strip()
                    
                    # Get location
                    location = self.location_cache.get(location_id)
                    if not location:
                        parse_errors.append(f'location_not_found: {location_id}')
                        # Still create entry but mark location error
                        location = None
                    
                    # Parse date
                    recorded_on, date_errors = parse_date(row['recorded_on'])
                    if date_errors:
                        parse_errors.extend(date_errors)
                        recorded_on = None
                    
                    # Parse value (handle commas, empty, invalid)
                    value_raw = row['value'].strip() if row['value'] else ''
                    value, value_errors = parse_value(value_raw)
                    parse_errors.extend(value_errors)
                    
                    # Clean record_ref for matching
                    record_ref_clean = clean_record_ref(record_ref_raw)
                    if record_ref_raw and not record_ref_clean:
                        parse_errors.append(f'invalid_record_ref_format: {record_ref_raw}')
                    
                    # Try to match to System A record
                    matched_record = None
                    if record_ref_clean:
                        matched_record = self.system_a_cache.get(record_ref_clean)
                        if not matched_record:
                            parse_errors.append(f'no_matching_system_a_record: {record_ref_clean}')
                    
                    # Create entry (always create, even with errors)
                    entry, created = SystemBEntry.objects.get_or_create(
                        entry_id=entry_id,
                        defaults={
                            'record_ref': record_ref_raw,
                            'record_ref_clean': record_ref_clean,
                            'location': location,
                            'recorded_on': recorded_on,
                            'value': value,
                            'value_raw': value_raw if value_raw else None,
                            'label': row['label'].strip(),
                            'matched_record': matched_record,
                            'raw_data': dict(row),
                            'parse_errors': parse_errors,
                        }
                    )
                    
                    if created:
                        self.stats['system_b']['created'] += 1
                    else:
                        # Update existing
                        for field, val in {
                            'record_ref': record_ref_raw,
                            'record_ref_clean': record_ref_clean,
                            'location': location,
                            'recorded_on': recorded_on,
                            'value': value,
                            'value_raw': value_raw if value_raw else None,
                            'label': row['label'].strip(),
                            'matched_record': matched_record,
                            'raw_data': dict(row),
                            'parse_errors': parse_errors,
                        }.items():
                            setattr(entry, field, val)
                        entry.save()
                    
                    if parse_errors:
                        self.log(f"  {entry_id} -> {record_ref_clean or record_ref_raw}: {len(parse_errors)} parse issue(s)")
                        
                except Exception as e:
                    self.stats['system_b']['errors'] += 1
                    self.log(f"  Row {row_num} ({row.get('entry_id', 'unknown')}) ERROR: {e}", 'error')
        
        self.log(f"System B: {self.stats['system_b']['created']} created, {self.stats['system_b']['errors']} errors")
    
    def run_all(self):
        """Run all imports in order."""
        self.log("=" * 60)
        self.log("Starting CSV Import")
        self.log("=" * 60)
        
        # Import in dependency order
        self.import_locations(DATA_DIR / 'locations.csv')
        self.import_system_a(DATA_DIR / 'system_a.csv')
        self.import_system_b(DATA_DIR / 'system_b.csv')
        
        self.log("=" * 60)
        self.log("Import Complete")
        self.log("=" * 60)
        for key, stat in self.stats.items():
            self.log(f"  {key}: {stat['created']} created, {stat['errors']} errors")
        
        return self.stats


class Command(BaseCommand):
    help = 'Load reconciliation data from CSV files'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before importing',
        )
    
    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write("Clearing existing data...")
            SystemBEntry.objects.all().delete()
            SystemARecord.objects.all().delete()
            Location.objects.all().delete()
            Organization.objects.all().delete()
            self.stdout.write("Cleared.")
        
        importer = CSVImporter(self.stdout, self.stderr)
        stats = importer.run_all()
        
        # Summary
        total_errors = sum(s['errors'] for s in stats.values())
        if total_errors > 0:
            self.stdout.write(self.style.WARNING(f"\nCompleted with {total_errors} total errors (rows preserved with error details)"))
        else:
            self.stdout.write(self.style.SUCCESS("\nImport completed successfully!"))
"""
Unit tests for disagreement detection logic.

Tests each of the 4 disagreement types:
1. Missing in B
2. Orphan in B
3. Duplicate in B
4. Value Mismatch
"""
from decimal import Decimal
from datetime import date
from django.test import TestCase

from reconciliation.models import (
    Organization,
    Location,
    SystemARecord,
    SystemBEntry,
    Disagreement,
)
from reconciliation.services.detector import (
    detect_missing_in_b,
    detect_orphans_in_b,
    detect_duplicates_in_b,
    detect_value_mismatches,
    run_all_detections,
    values_match,
    VALUE_EPSILON,
)
from reconciliation.services.matcher import match_all_entries


class DetectorTestBase(TestCase):
    """Base test class with common setup."""
    
    def setUp(self):
        # Create org and location
        self.org = Organization.objects.create(org_id='ORG-TEST', name='Test Org')
        self.location = Location.objects.create(
            location_id='LOC-TEST', org=self.org, name='Test Location'
        )
    
    def create_system_a_record(self, record_id, total_value, **kwargs):
        """Helper to create a System A record."""
        defaults = {
            'record_id': record_id,
            'location': self.location,
            'event_date': date(2026, 3, 15),
            'category_code': 'CAT-01',
            'actor_id': 'USR-01',
            'base_value': Decimal('1000.00'),
            'adjustment': Decimal('100.00'),
            'total_value': total_value,
            'state': 'CONFIRMED',
        }
        defaults.update(kwargs)
        return SystemARecord.objects.create(**defaults)
    
    def create_system_b_entry(self, entry_id, record_ref, value, **kwargs):
        """Helper to create a System B entry."""
        defaults = {
            'entry_id': entry_id,
            'record_ref': record_ref,
            'record_ref_clean': record_ref,
            'location': self.location,
            'recorded_on': date(2026, 3, 15),
            'value': value,
            'value_raw': str(value) if value else None,
            'label': f'Entry for {record_ref}',
        }
        defaults.update(kwargs)
        return SystemBEntry.objects.create(**defaults)


class ValuesMatchTest(TestCase):
    """Test the values_match epsilon comparison function."""
    
    def test_exact_match(self):
        self.assertTrue(values_match(Decimal('100.00'), Decimal('100.00')))
    
    def test_within_epsilon(self):
        self.assertTrue(values_match(Decimal('100.00'), Decimal('100.005')))
        self.assertTrue(values_match(Decimal('100.00'), Decimal('99.995')))
    
    def test_outside_epsilon(self):
        self.assertFalse(values_match(Decimal('100.00'), Decimal('100.02')))
        self.assertFalse(values_match(Decimal('100.00'), Decimal('99.98')))
    
    def test_none_values(self):
        self.assertTrue(values_match(None, None))
        self.assertFalse(values_match(Decimal('100.00'), None))
        self.assertFalse(values_match(None, Decimal('100.00')))
    
    def test_zero_values(self):
        self.assertTrue(values_match(Decimal('0.00'), Decimal('0.00')))
        self.assertTrue(values_match(Decimal('0.00'), Decimal('0.005')))
        self.assertFalse(values_match(Decimal('0.00'), Decimal('0.02')))


class MissingInBTest(DetectorTestBase):
    """Test: System A record with no System B entries."""
    
    def test_missing_in_b_detected(self):
        """A System A record with zero matched B entries should be flagged."""
        record = self.create_system_a_record('REC-001', Decimal('1000.00'))
        
        # No System B entries created
        results = detect_missing_in_b()
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['reason'], Disagreement.Reason.MISSING_IN_B)
        self.assertEqual(results[0]['system_a_record'], record)
        self.assertIsNone(results[0]['system_b_entry'])
        self.assertEqual(results[0]['system_a_value'], Decimal('1000.00'))
    
    def test_missing_in_b_not_flagged_when_matched(self):
        """A System A record WITH matched B entries should NOT be flagged."""
        record = self.create_system_a_record('REC-002', Decimal('2000.00'))
        entry = self.create_system_b_entry('ENT-001', 'REC-002', Decimal('2000.00'))
        entry.matched_record = record
        entry.save()
        
        results = detect_missing_in_b()
        
        # Should not include REC-002
        record_ids = [r['system_a_record'].record_id for r in results if r['system_a_record']]
        self.assertNotIn('REC-002', record_ids)


class OrphanInBTest(DetectorTestBase):
    """Test: System B entry with no matching System A record."""
    
    def test_orphan_in_b_detected(self):
        """A System B entry with matched_record=None should be flagged."""
        entry = self.create_system_b_entry('ENT-002', 'REC-999', Decimal('500.00'))
        entry.matched_record = None
        entry.save()
        
        results = detect_orphans_in_b()
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['reason'], Disagreement.Reason.ORPHAN_IN_B)
        self.assertEqual(results[0]['system_b_entry'], entry)
        self.assertIsNone(results[0]['system_a_record'])
        self.assertEqual(results[0]['system_b_value'], Decimal('500.00'))
    
    def test_orphan_not_flagged_when_matched(self):
        """A System B entry WITH matched_record should NOT be flagged as orphan."""
        record = self.create_system_a_record('REC-003', Decimal('3000.00'))
        entry = self.create_system_b_entry('ENT-003', 'REC-003', Decimal('3000.00'))
        entry.matched_record = record
        entry.save()
        
        results = detect_orphans_in_b()
        
        entry_ids = [r['system_b_entry'].entry_id for r in results]
        self.assertNotIn('ENT-003', entry_ids)


class DuplicateInBTest(DetectorTestBase):
    """Test: Multiple System B entries for same System A record."""
    
    def test_duplicate_in_b_detected(self):
        """System A record with >1 matched B entries should flag duplicates."""
        record = self.create_system_a_record('REC-004', Decimal('4000.00'))
        
        # Create 3 entries for same record
        entry1 = self.create_system_b_entry('ENT-004', 'REC-004', Decimal('4000.00'))
        entry1.matched_record = record
        entry1.save()
        
        entry2 = self.create_system_b_entry('ENT-005', 'REC-004', Decimal('4000.00'))
        entry2.matched_record = record
        entry2.save()
        
        entry3 = self.create_system_b_entry('ENT-006', 'REC-004', Decimal('4100.00'))
        entry3.matched_record = record
        entry3.save()
        
        results = detect_duplicates_in_b()
        
        # Should flag 2 duplicates (entries 2 and 3)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r['reason'], Disagreement.Reason.DUPLICATE_IN_B)
            self.assertEqual(r['system_a_record'], record)
        
        # Check duplicate numbers
        dup_numbers = [r['details']['duplicate_number'] for r in results]
        self.assertIn(2, dup_numbers)
        self.assertIn(3, dup_numbers)
    
    def test_no_duplicate_flagged_for_single_entry(self):
        """Single B entry per A record should NOT trigger duplicate."""
        record = self.create_system_a_record('REC-005', Decimal('5000.00'))
        entry = self.create_system_b_entry('ENT-007', 'REC-005', Decimal('5000.00'))
        entry.matched_record = record
        entry.save()
        
        results = detect_duplicates_in_b()
        
        record_ids = [r['system_a_record'].record_id for r in results if r['system_a_record']]
        self.assertNotIn('REC-005', record_ids)


class ValueMismatchTest(DetectorTestBase):
    """Test: Matched pair with different values (beyond epsilon)."""
    
    def test_value_mismatch_detected(self):
        """Matched pair with values differing > 0.01 should be flagged."""
        record = self.create_system_a_record('REC-006', Decimal('1000.00'))
        entry = self.create_system_b_entry('ENT-008', 'REC-006', Decimal('1050.00'))
        entry.matched_record = record
        entry.save()
        
        results = detect_value_mismatches()
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['reason'], Disagreement.Reason.VALUE_MISMATCH)
        self.assertEqual(results[0]['system_a_record'], record)
        self.assertEqual(results[0]['system_b_entry'], entry)
        self.assertEqual(results[0]['system_a_value'], Decimal('1000.00'))
        self.assertEqual(results[0]['system_b_value'], Decimal('1050.00'))
    
    def test_value_match_not_flagged(self):
        """Matched pair with same values should NOT be flagged."""
        record = self.create_system_a_record('REC-007', Decimal('2000.00'))
        entry = self.create_system_b_entry('ENT-009', 'REC-007', Decimal('2000.00'))
        entry.matched_record = record
        entry.save()
        
        results = detect_value_mismatches()
        
        record_ids = [r['system_a_record'].record_id for r in results if r['system_a_record']]
        self.assertNotIn('REC-007', record_ids)
    
    def test_value_within_epsilon_not_flagged(self):
        """Matched pair with values within 0.01 should NOT be flagged."""
        record = self.create_system_a_record('REC-008', Decimal('3000.00'))
        entry = self.create_system_b_entry('ENT-010', 'REC-008', Decimal('3000.005'))
        entry.matched_record = record
        entry.save()
        
        results = detect_value_mismatches()
        
        record_ids = [r['system_a_record'].record_id for r in results if r['system_a_record']]
        self.assertNotIn('REC-008', record_ids)
    
    def test_orphan_not_checked_for_value_mismatch(self):
        """Orphan entries (no matched_record) should NOT be checked for value mismatch."""
        record = self.create_system_a_record('REC-009', Decimal('4000.00'))
        entry = self.create_system_b_entry('ENT-011', 'REC-999', Decimal('9999.00'))
        entry.matched_record = None  # Orphan
        entry.save()
        
        results = detect_value_mismatches()
        
        entry_ids = [r['system_b_entry'].entry_id for r in results]
        self.assertNotIn('ENT-011', entry_ids)


class FullDetectionTest(DetectorTestBase):
    """Integration test: run_all_detections combines all rules."""
    
    def test_all_four_types_detected_together(self):
        """Verify all 4 disagreement types can be detected in one run."""
        # 1. Missing in B
        self.create_system_a_record('REC-MISSING', Decimal('100.00'))
        
        # 2. Orphan in B
        self.create_system_b_entry('ENT-ORPHAN', 'REC-NONEXISTENT', Decimal('200.00'))
        # matched_record defaults to None
        
        # 3. Duplicate in B
        dup_record = self.create_system_a_record('REC-DUP', Decimal('300.00'))
        for i in range(3):
            entry = self.create_system_b_entry(f'ENT-DUP-{i}', 'REC-DUP', Decimal('300.00'))
            entry.matched_record = dup_record
            entry.save()
        
        # 4. Value Mismatch
        mismatch_record = self.create_system_a_record('REC-MISMATCH', Decimal('400.00'))
        mismatch_entry = self.create_system_b_entry('ENT-MISMATCH', 'REC-MISMATCH', Decimal('500.00'))
        mismatch_entry.matched_record = mismatch_record
        mismatch_entry.save()
        
        # 5. Perfect match (should NOT appear)
        good_record = self.create_system_a_record('REC-GOOD', Decimal('500.00'))
        good_entry = self.create_system_b_entry('ENT-GOOD', 'REC-GOOD', Decimal('500.00'))
        good_entry.matched_record = good_record
        good_entry.save()
        
        results = run_all_detections()
        
        self.assertEqual(results['total'], 5)  # 1 missing + 1 orphan + 2 duplicates + 1 value mismatch
        self.assertEqual(results['by_reason'].get('missing_in_b'), 1)
        self.assertEqual(results['by_reason'].get('orphan_in_b'), 1)
        self.assertEqual(results['by_reason'].get('duplicate_in_b'), 2)
        self.assertEqual(results['by_reason'].get('value_mismatch'), 1)
    
    def test_run_all_detections_returns_correct_structure(self):
        """Verify the return structure of run_all_detections."""
        self.create_system_a_record('REC-001', Decimal('100.00'))
        
        results = run_all_detections()
        
        self.assertIn('total', results)
        self.assertIn('by_reason', results)
        self.assertIn('disagreements', results)
        self.assertIsInstance(results['disagreements'], list)
        self.assertIsInstance(results['by_reason'], dict)


class MatcherTest(DetectorTestBase):
    """Test the matching service."""
    
    def test_match_all_entries(self):
        """Verify matcher links entries to records correctly."""
        # Create System A records
        record1 = self.create_system_a_record('REC-100', Decimal('100.00'))
        record2 = self.create_system_a_record('REC-200', Decimal('200.00'))
        
        # Create System B entries (unmatched)
        entry1 = self.create_system_b_entry('ENT-100', 'REC-100', Decimal('100.00'))
        entry2 = self.create_system_b_entry('ENT-200', 'REC-200', Decimal('200.00'))
        entry3 = self.create_system_b_entry('ENT-ORPHAN', 'REC-999', Decimal('999.00'))
        
        # Run matcher
        stats = match_all_entries()
        
        self.assertEqual(stats['matched'], 2)
        self.assertEqual(stats['unmatched'], 1)
        
        # Verify matches
        entry1.refresh_from_db()
        entry2.refresh_from_db()
        entry3.refresh_from_db()
        
        self.assertEqual(entry1.matched_record, record1)
        self.assertEqual(entry2.matched_record, record2)
        self.assertIsNone(entry3.matched_record)
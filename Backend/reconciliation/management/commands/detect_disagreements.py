
"""

Management command to run disagreement detection.
"""
from django.core.management.base import BaseCommand

from reconciliation.services.matcher import match_all_entries, get_match_stats
from reconciliation.services.detector import run_full_detection


class Command(BaseCommand):
    help = 'Run disagreement detection between System A and System B'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show detection results without saving to database',
        )
        parser.add_argument(
            '--skip-matching',
            action='store_true',
            help='Skip the matching step (use existing matches)',
        )
    
    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write("Disagreement Detection")
        self.stdout.write("=" * 60)
        
        # Step 1: Match entries
        if not options['skip_matching']:
            self.stdout.write("\n[1/2] Matching System B entries to System A records...")
            match_stats = match_all_entries()
            self.stdout.write(f"  Total entries: {match_stats['total_entries']}")
            self.stdout.write(f"  Already matched: {match_stats['already_matched']}")
            self.stdout.write(f"  Newly matched: {match_stats['newly_matched']}")
            self.stdout.write(f"  Unmatched: {match_stats['unmatched']}")
        else:
            self.stdout.write("\n[1/2] Skipping matching (using existing)")
            match_stats = get_match_stats()
            self.stdout.write(f"  Matched: {match_stats['matched']}, Unmatched: {match_stats['unmatched']}")
        
        # Step 2: Detect disagreements
        self.stdout.write("\n[2/2] Detecting disagreements...")
        
        if options['dry_run']:
            from reconciliation.services.detector import run_all_detections
            results = run_all_detections()
            self.stdout.write(f"  Total disagreements found: {results['total']}")
            for reason, count in results['by_reason'].items():
                self.stdout.write(f"    {reason}: {count}")
        else:
            results = run_full_detection()
            self.stdout.write(f"  Total disagreements: {results['total']}")
            self.stdout.write(f"  Saved to DB: {results['created']}")
            self.stdout.write(f"  Previous deleted: {results['deleted']}")
            if results['skipped']:
                self.stdout.write(f"  Skipped (no org): {results['skipped']}")
            for reason, count in results['by_reason'].items():
                self.stdout.write(f"    {reason}: {count}")
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Detection complete!"))
        self.stdout.write("=" * 60)
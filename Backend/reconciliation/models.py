from django.db import models
from decimal import Decimal


class Organization(models.Model):
    """
    Represents a tenant/organization. Each location belongs to exactly one org.
    This is the tenant boundary - data must never leak across orgs.
    """
    org_id = models.CharField(max_length=20, unique=True, help_text="e.g., ORG-A, ORG-B")
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['org_id']

    def __str__(self):
        return f"{self.org_id} - {self.name}"


class Location(models.Model):
    """
    Physical/business location. Belongs to exactly one organization.
    """
    location_id = models.CharField(max_length=20, unique=True, help_text="e.g., LOC-101")
    org = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name='locations'
    )
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['location_id']

    def __str__(self):
        return f"{self.location_id} - {self.name} ({self.org.org_id})"


class SystemARecord(models.Model):
    """
    System A record - one row per event as recorded by System A.
    record_id is the canonical identifier.
    """
    record_id = models.CharField(max_length=20, unique=True, help_text="e.g., REC-1001")
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='system_a_records'
    )
    event_date = models.DateField()
    category_code = models.CharField(max_length=20, help_text="e.g., CAT-01")
    actor_id = models.CharField(max_length=20, blank=True, null=True, help_text="e.g., USR-11")
    base_value = models.DecimalField(max_digits=15, decimal_places=2)
    adjustment = models.DecimalField(max_digits=15, decimal_places=2)
    total_value = models.DecimalField(max_digits=15, decimal_places=2)
    state = models.CharField(max_length=20, help_text="e.g., CONFIRMED, VOIDED")
    raw_data = models.JSONField(default=dict, help_text="Original CSV row for audit")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['record_id']

    def __str__(self):
        return f"{self.record_id} - {self.total_value} ({self.location.location_id})"


class SystemBEntry(models.Model):
    """
    System B entry - one row per entry as recorded by System B.
    record_ref points to System A but is dirty (multiple formats, typos, etc.).
    There may be more than one entry per System A record.
    """
    entry_id = models.CharField(max_length=50, unique=True, help_text="e.g., ENT/2026/4001")
    record_ref = models.CharField(max_length=50, help_text="Raw reference to System A record_id")
    record_ref_clean = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Normalized record_ref for matching (e.g., REC-1001)"
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='system_b_entries'
    )
    recorded_on = models.DateField()
    value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Parsed numeric value"
    )
    value_raw = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Original value string before parsing (e.g., '1,25,400.00')"
    )
    label = models.CharField(max_length=200)
    matched_record = models.ForeignKey(
        SystemARecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='system_b_entries',
        help_text="Linked System A record after matching"
    )
    raw_data = models.JSONField(default=dict, help_text="Original CSV row for audit")
    parse_errors = models.JSONField(
        default=list,
        blank=True,
        help_text="List of parsing issues encountered"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['entry_id']

    def __str__(self):
        ref = self.record_ref_clean or self.record_ref
        return f"{self.entry_id} -> {ref} ({self.value})"


class Disagreement(models.Model):
    """
    A detected disagreement between System A and System B.
    Each disagreement has a reason, both systems' values, and location/org context.
    """
    class Reason(models.TextChoices):
        MISSING_IN_B = 'missing_in_b', 'Missing in System B'
        ORPHAN_IN_B = 'orphan_in_b', 'Orphan in System B'
        DUPLICATE_IN_B = 'duplicate_in_b', 'Duplicate in System B'
        VALUE_MISMATCH = 'value_mismatch', 'Value Mismatch'

    system_a_record = models.ForeignKey(
        SystemARecord,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='disagreements'
    )
    system_b_entry = models.ForeignKey(
        SystemBEntry,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='disagreements'
    )
    reason = models.CharField(max_length=30, choices=Reason.choices)
    system_a_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    system_b_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='disagreements')
    org = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='disagreements')
    details = models.JSONField(default=dict, help_text="Additional context about the disagreement")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-system_a_value', 'reason']
        indexes = [
            models.Index(fields=['reason', 'org']),
            models.Index(fields=['location', 'reason']),
        ]

    def __str__(self):
        a_val = f"{self.system_a_value}" if self.system_a_value else "N/A"
        b_val = f"{self.system_b_value}" if self.system_b_value else "N/A"
        return f"[{self.reason}] {self.location.location_id}: A={a_val} vs B={b_val}"

"""
DRF Serializers for Reconciliation API.
"""
from rest_framework import serializers

from reconciliation.models import (
    Disagreement,
    Location,
    Organization,
    SystemARecord,
    SystemBEntry,
)


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['org_id', 'name']


class LocationSerializer(serializers.ModelSerializer):
    org = OrganizationSerializer(read_only=True)
    
    class Meta:
        model = Location
        fields = ['location_id', 'name', 'org']


class DisagreementSerializer(serializers.ModelSerializer):
    """Serializer for disagreement list/detail views."""
    location = LocationSerializer(read_only=True)
    org = OrganizationSerializer(read_only=True)
    system_a_record_id = serializers.CharField(
        source='system_a_record.record_id', 
        read_only=True,
        allow_null=True
    )
    system_b_entry_id = serializers.CharField(
        source='system_b_entry.entry_id', 
        read_only=True,
        allow_null=True
    )
    reason_display = serializers.CharField(source='get_reason_display', read_only=True)
    
    class Meta:
        model = Disagreement
        fields = [
            'id',
            'reason',
            'reason_display',
            'system_a_record_id',
            'system_b_entry_id',
            'system_a_value',
            'system_b_value',
            'location',
            'org',
            'details',
            'created_at',
        ]


class DisagreementStatsSerializer(serializers.Serializer):
    """Serializer for disagreement statistics."""
    reason = serializers.CharField()
    reason_display = serializers.CharField()
    count = serializers.IntegerField()


class SystemARecordSerializer(serializers.ModelSerializer):
    location = serializers.CharField(source='location.location_id', read_only=True)
    org = serializers.CharField(source='location.org.org_id', read_only=True)
    matched_entries = serializers.ListField(read_only=True)
    reasons = serializers.ListField(read_only=True)

    class Meta:
        model = SystemARecord
        fields = [
            'record_id', 'total_value', 'event_date', 'state', 'category_code',
            'location', 'org', 'matched_entries', 'reasons',
        ]


class SystemBEntrySerializer(serializers.ModelSerializer):
    location = serializers.CharField(source='location.location_id', read_only=True)
    org = serializers.CharField(source='location.org.org_id', read_only=True)
    matched_record = serializers.CharField(
        source='matched_record.record_id', read_only=True, allow_null=True
    )
    reasons = serializers.ListField(read_only=True)

    class Meta:
        model = SystemBEntry
        fields = [
            'entry_id', 'record_ref', 'value', 'recorded_on', 'label',
            'location', 'org', 'matched_record', 'reasons', 'parse_errors',
        ]
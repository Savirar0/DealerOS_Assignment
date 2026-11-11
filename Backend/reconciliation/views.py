"""
API Views for Reconciliation disagreements.
"""
from django.db.models import Count
from rest_framework import generics, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from reconciliation.models import Disagreement, SystemARecord, SystemBEntry
from reconciliation.serializers import (
    DisagreementSerializer,
    DisagreementStatsSerializer,
    SystemARecordSerializer,
    SystemBEntrySerializer,
)


class DisagreementListView(generics.ListAPIView):
    """
    List all disagreements with filtering and sorting.
    
    Query Parameters:
    - reason: Filter by reason (missing_in_b, orphan_in_b, duplicate_in_b, value_mismatch)
    - org: Filter by org_id (ORG-A, ORG-B)
    - location: Filter by location_id (LOC-101, etc.)
    - ordering: Sort by field (system_a_value, system_b_value, created_at, reason)
                Prefix with '-' for descending (e.g., -system_a_value)
    - page: Page number (default page size: 100)
    """
    serializer_class = DisagreementSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['reason', 'org__org_id', 'location__location_id']
    ordering_fields = ['system_a_value', 'system_b_value', 'created_at', 'reason']
    ordering = ['-system_a_value']  # Default: highest value first
    
    def get_queryset(self):
        return Disagreement.objects.select_related(
            'location', 'org', 'system_a_record', 'system_b_entry'
        ).all()


class DisagreementDetailView(generics.RetrieveAPIView):
    """Retrieve a single disagreement by ID."""
    serializer_class = DisagreementSerializer
    queryset = Disagreement.objects.select_related(
        'location', 'org', 'system_a_record', 'system_b_entry'
    ).all()


class DisagreementStatsView(APIView):
    """
    Get disagreement counts grouped by reason.
    
    Returns: [
        {"reason": "missing_in_b", "reason_display": "Missing in System B", "count": 2},
        ...
    ]
    """
    def get(self, request):
        stats = Disagreement.objects.values('reason').annotate(count=Count('id')).order_by('-count')
        
        # Add display names
        reason_display_map = dict(Disagreement.Reason.choices)
        for stat in stats:
            stat['reason_display'] = reason_display_map.get(stat['reason'], stat['reason'])
        
        serializer = DisagreementStatsSerializer(stats, many=True)
        return Response(serializer.data)


class RecordsView(APIView):
    """Return every imported source row, including clean matches."""

    def get(self, request):
        disagreements = Disagreement.objects.values(
            'system_a_record_id', 'system_b_entry_id', 'reason'
        )
        a_reasons = {}
        b_reasons = {}
        for item in disagreements:
            if item['system_a_record_id']:
                a_reasons.setdefault(item['system_a_record_id'], []).append(item['reason'])
            if item['system_b_entry_id']:
                b_reasons.setdefault(item['system_b_entry_id'], []).append(item['reason'])

        system_a = list(SystemARecord.objects.select_related(
            'location__org'
        ).prefetch_related('system_b_entries').all())
        for record in system_a:
            record.matched_entries = [
                entry.entry_id for entry in record.system_b_entries.all()
            ]
            record.reasons = sorted(set(a_reasons.get(record.id, [])))

        system_b = list(SystemBEntry.objects.select_related(
            'location__org', 'matched_record'
        ).all())
        for entry in system_b:
            entry.reasons = sorted(set(b_reasons.get(entry.id, [])))

        return Response({
            'system_a': SystemARecordSerializer(system_a, many=True).data,
            'system_b': SystemBEntrySerializer(system_b, many=True).data,
            'counts': {
                'system_a': len(system_a),
                'system_b': len(system_b),
                'disagreements': len(disagreements),
            },
        })

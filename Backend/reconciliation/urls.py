"""
URL routing for Reconciliation API.
"""
from django.urls import path
from reconciliation.views import (
    DisagreementListView,
    DisagreementDetailView,
    DisagreementStatsView,
    RecordsView,
)

urlpatterns = [
    path('disagreements/', DisagreementListView.as_view(), name='disagreement-list'),
    path('disagreements/<int:pk>/', DisagreementDetailView.as_view(), name='disagreement-detail'),
    path('disagreements/stats/', DisagreementStatsView.as_view(), name='disagreement-stats'),
    path('records/', RecordsView.as_view(), name='records'),
]
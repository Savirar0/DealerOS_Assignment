/**
 * Disagreements Table Component
 * Displays reconciliation disagreements with filtering and sorting
 */
import { useState, useEffect, useCallback } from 'react';
import { disagreementsApi } from '../api';

const REASON_OPTIONS = [
  { value: '', label: 'All Reasons' },
  { value: 'missing_in_b', label: 'Missing in System B' },
  { value: 'orphan_in_b', label: 'Orphan in System B' },
  { value: 'duplicate_in_b', label: 'Duplicate in System B' },
  { value: 'value_mismatch', label: 'Value Mismatch' },
];

function formatCurrency(value) {
  if (value === null || value === undefined) return '—';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(num);
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function getReasonBadgeClass(reason) {
  const classes = {
    missing_in_b: 'badge-missing',
    orphan_in_b: 'badge-orphan',
    duplicate_in_b: 'badge-duplicate',
    value_mismatch: 'badge-mismatch',
  };
  return classes[reason] || '';
}

export default function DisagreementsTable() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ reason: '' });
  const [sortConfig, setSortConfig] = useState({ key: 'system_a_value', direction: 'desc' });
  const [stats, setStats] = useState([]);

  // Fetch data
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (filters.reason) params.reason = filters.reason;
      
      // Build ordering param
      const orderPrefix = sortConfig.direction === 'desc' ? '-' : '';
      params.ordering = `${orderPrefix}${sortConfig.key}`;
      
      const response = await disagreementsApi.list(params);
      setData(response.data.results || response.data);
    } catch (err) {
      setError(err.message || 'Failed to load disagreements');
      console.error('Fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [filters.reason, sortConfig.direction, sortConfig.key]);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    try {
      const response = await disagreementsApi.stats();
      setStats(response.data);
    } catch (err) {
      console.error('Stats fetch error:', err);
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      await Promise.all([fetchData(), fetchStats()]);
    };
    loadData();
  }, [fetchData, fetchStats]);

  // Handle sort click
  const handleSort = (key) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  };

  // Handle filter change
  const handleFilterChange = (e) => {
    setFilters(prev => ({ ...prev, reason: e.target.value }));
  };

  // Clear filters
  const clearFilters = () => {
    setFilters({ reason: '' });
  };

  if (loading) {
    return (
      <div className="table-container">
        <div className="loading">Loading disagreements...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="table-container">
        <div className="error">Error: {error}</div>
      </div>
    );
  }

  const hasFilters = filters.reason;

  return (
    <div className="table-container">
      {/* Header with title and stats */}
      <div className="table-header">
        <h2>System Disagreements</h2>
        <div className="stats-summary">
          {stats.map(s => (
            <span key={s.reason} className={`stat-badge ${s.reason}`}>
              {s.reason_display}: {s.count}
            </span>
          ))}
        </div>
      </div>

      {/* Filter Bar */}
      <div className="filter-bar">
        <div className="filter-group">
          <label htmlFor="reason-filter">Filter by Reason:</label>
          <select
            id="reason-filter"
            value={filters.reason}
            onChange={handleFilterChange}
          >
            {REASON_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        {hasFilters && (
          <button className="btn-clear" onClick={clearFilters}>Clear Filter</button>
        )}
        <div className="result-count">
          {data.length} disagreement{data.length !== 1 ? 's' : ''} found
        </div>
      </div>

      {/* Table */}
      <div className="table-wrapper">
        <table className="disagreements-table">
          <thead>
            <tr>
              <th onClick={() => handleSort('reason')} className="sortable">
                Reason {sortConfig.key === 'reason' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th>System A Record</th>
              <th>System B Entry</th>
              <th onClick={() => handleSort('system_a_value')} className="sortable numeric">
                System A Value {sortConfig.key === 'system_a_value' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th onClick={() => handleSort('system_b_value')} className="sortable numeric">
                System B Value {sortConfig.key === 'system_b_value' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
              <th>Location</th>
              <th>Organization</th>
              <th onClick={() => handleSort('created_at')} className="sortable">
                Detected {sortConfig.key === 'created_at' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </th>
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              <tr>
                <td colSpan="8" className="empty-state">No disagreements found</td>
              </tr>
            ) : (
              data.map(item => (
                <tr key={item.id}>
                  <td>
                    <span className={`reason-badge ${getReasonBadgeClass(item.reason)}`}>
                      {item.reason_display}
                    </span>
                  </td>
                  <td className="record-id">
                    {item.system_a_record_id || '—'}
                  </td>
                  <td className="record-id">
                    {item.system_b_entry_id || '—'}
                  </td>
                  <td className="numeric">{formatCurrency(item.system_a_value)}</td>
                  <td className="numeric">{formatCurrency(item.system_b_value)}</td>
                  <td>{item.location?.location_id || '—'}</td>
                  <td>{item.org?.org_id || '—'}</td>
                  <td className="date">{formatDate(item.created_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
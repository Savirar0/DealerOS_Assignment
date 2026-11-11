/**
 * Records Table Component
 * Displays all System A records and System B entries in a combined view
 */
import { useState, useEffect, useCallback } from 'react';
import { recordsApi } from '../api';

function formatCurrency(value) {
  if (value === null || value === undefined) return '—';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(num);
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

export default function RecordsTable() {
  const [systemAData, setSystemAData] = useState([]);
  const [systemBData, setSystemBData] = useState([]);
  const [disagreements, setDisagreements] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('systemA'); // 'systemA', 'systemB', 'all'

  // Fetch all data
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await recordsApi.list();
      const { system_a: systemA, system_b: systemB, counts } = response.data;
      setSystemAData(systemA);
      setSystemBData(systemB);
      setDisagreements(counts.disagreements);

    } catch (err) {
      setError(err.message || 'Failed to load records');
      console.error('Fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const loadRecords = async () => {
      await fetchData();
    };
    loadRecords();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="table-container">
        <div className="loading">Loading records...</div>
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

  const renderReasonBadges = (reasons) => (
    <span>
      {reasons.map(r => (
        <span key={r} className={`reason-badge ${getReasonBadgeClass(r)}`}>
          {r.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
        </span>
      ))}
    </span>
  );

  return (
    <div className="table-container">
      {/* Header */}
      <div className="table-header">
        <h2>All Records View</h2>
        <div className="stats-summary">
          <span className="stat-badge">System A: {systemAData.length} records</span>
          <span className="stat-badge">System B: {systemBData.length} entries</span>
          <span className="stat-badge">Disagreements: {disagreements}</span>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="tab-navigation">
        <button 
          className={activeTab === 'systemA' ? 'active' : ''}
          onClick={() => setActiveTab('systemA')}
        >
          System A Records ({systemAData.length})
        </button>
        <button 
          className={activeTab === 'systemB' ? 'active' : ''}
          onClick={() => setActiveTab('systemB')}
        >
          System B Entries ({systemBData.length})
        </button>
        <button 
          className={activeTab === 'all' ? 'active' : ''}
          onClick={() => setActiveTab('all')}
        >
          Combined View
        </button>
      </div>

      {/* System A Table */}
      {activeTab === 'systemA' && (
        <div className="table-wrapper">
          <table className="records-table">
            <thead>
              <tr>
                <th>Record ID</th>
                <th>System A Value</th>
                <th>Location</th>
                <th>Organization</th>
                <th>Matched B Entries</th>
                <th>Disagreement Reasons</th>
              </tr>
            </thead>
            <tbody>
              {systemAData.length === 0 ? (
                <tr><td colSpan="6" className="empty-state">No System A records found</td></tr>
              ) : (
                systemAData.map(item => (
                  <tr key={item.record_id}>
                    <td className="record-id">{item.record_id}</td>
                    <td className="numeric">{formatCurrency(item.system_a_value)}</td>
                    <td>{item.location}</td>
                    <td>{item.org}</td>
                    <td>
                      {item.matched_entries.length > 0 ? (
                        <span className="matched-count">{item.matched_entries.length} entr{item.matched_entries.length === 1 ? 'y' : 'ies'}</span>
                      ) : (
                        <span className="no-match">No matches</span>
                      )}
                    </td>
                    <td>{renderReasonBadges(item.reasons)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* System B Table */}
      {activeTab === 'systemB' && (
        <div className="table-wrapper">
          <table className="records-table">
            <thead>
              <tr>
                <th>Entry ID</th>
                <th>System B Value</th>
                <th>Location</th>
                <th>Organization</th>
                <th>Matched A Record</th>
                <th>Disagreement Reasons</th>
              </tr>
            </thead>
            <tbody>
              {systemBData.length === 0 ? (
                <tr><td colSpan="6" className="empty-state">No System B entries found</td></tr>
              ) : (
                systemBData.map(item => (
                  <tr key={item.entry_id}>
                    <td className="record-id">{item.entry_id}</td>
                    <td className="numeric">{formatCurrency(item.system_b_value)}</td>
                    <td>{item.location}</td>
                    <td>{item.org}</td>
                    <td>
                      {item.matched_record !== '—' ? (
                        <span className="record-id">{item.matched_record}</span>
                      ) : (
                        <span className="no-match">Orphan</span>
                      )}
                    </td>
                    <td>{renderReasonBadges(item.reasons)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Combined View */}
      {activeTab === 'all' && (
        <div className="table-wrapper">
          <table className="records-table">
            <thead>
              <tr>
                <th>System</th>
                <th>ID</th>
                <th>Value</th>
                <th>Location</th>
                <th>Organization</th>
                <th>Counterpart</th>
                <th>Issues</th>
              </tr>
            </thead>
            <tbody>
              {/* System A Records */}
              {systemAData.map(item => (
                <tr key={`A-${item.record_id}`} className="system-a-row">
                  <td><span className="system-badge system-a">A</span></td>
                  <td className="record-id">{item.record_id}</td>
                  <td className="numeric">{formatCurrency(item.system_a_value)}</td>
                  <td>{item.location}</td>
                  <td>{item.org}</td>
                  <td>
                    {item.matched_entries.length > 0 ? (
                      item.matched_entries.map(e => <span key={e} className="counterpart">{e}</span>)
                    ) : (
                      <span className="no-match">—</span>
                    )}
                  </td>
                  <td>{renderReasonBadges(item.reasons)}</td>
                </tr>
              ))}
              {/* System B Entries */}
              {systemBData.map(item => (
                <tr key={`B-${item.entry_id}`} className="system-b-row">
                  <td><span className="system-badge system-b">B</span></td>
                  <td className="record-id">{item.entry_id}</td>
                  <td className="numeric">{formatCurrency(item.system_b_value)}</td>
                  <td>{item.location}</td>
                  <td>{item.org}</td>
                  <td>
                    {item.matched_record !== '—' ? (
                      <span className="record-id">{item.matched_record}</span>
                    ) : (
                      <span className="no-match">Orphan</span>
                    )}
                  </td>
                  <td>{renderReasonBadges(item.reasons)}</td>
                </tr>
              ))}
              {(systemAData.length === 0 && systemBData.length === 0) && (
                <tr><td colSpan="7" className="empty-state">No records found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
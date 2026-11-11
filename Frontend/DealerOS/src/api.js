/**
 * API Client for DealerOS Backend
 */
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

export const disagreementsApi = {
  /**
   * Fetch disagreements with optional filters and sorting
   * @param {Object} params - Query parameters
   * @param {string} params.reason - Filter by reason
   * @param {string} params.org - Filter by org_id
   * @param {string} params.location - Filter by location_id
   * @param {string} params.ordering - Sort field (prefix with - for desc)
   * @param {number} params.page - Page number
   */
  list: (params = {}) => api.get('/disagreements/', { params }),

  /**
   * Fetch single disagreement by ID
   */
  detail: (id) => api.get(`/disagreements/${id}/`),

  /**
   * Fetch disagreement stats (counts by reason)
   */
  stats: () => api.get('/disagreements/stats/'),
};

export const recordsApi = {
  list: () => api.get('/records/'),
};

export default api;
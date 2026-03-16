import axios from 'axios';

const BASE_URL = 'http://localhost:8000/api/v1';

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Attach access token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// On 401 → attempt refresh, else logout
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    // Extract and format FastAPI validation errors
    if (err.response?.data?.detail) {
      if (Array.isArray(err.response.data.detail)) {
        err.response.data.detail = err.response.data.detail.map(d => 
          typeof d === 'string' ? d : (d.msg || JSON.stringify(d))
        ).join(', ');
      } else if (typeof err.response.data.detail === 'object') {
        err.response.data.detail = JSON.stringify(err.response.data.detail);
      }
    }

    const original = err.config;
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refresh = localStorage.getItem('refresh_token');
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE_URL}/auth/refresh`, { refresh_token: refresh });
          localStorage.setItem('access_token', data.access_token);
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return api(original);
        } catch {
          localStorage.clear();
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(err);
  }
);

// Auth
export const authApi = {
  register: (d) => api.post('/auth/register', d),
  login: (d) => api.post('/auth/login', d),
  logout: (refresh_token) => api.post('/auth/logout', { refresh_token }),
  me: () => api.get('/auth/me'),
};

// Roadmaps
export const roadmapApi = {
  list: (params) => api.get('/roadmaps', { params }),
  get: (id) => api.get(`/roadmaps/${id}`),
  create: (d) => api.post('/roadmaps', d),
  update: (id, d) => api.patch(`/roadmaps/${id}`, d),
  delete: (id) => api.delete(`/roadmaps/${id}`),
  publish: (id) => api.post(`/roadmaps/${id}/publish`),
  generate: (d) => api.post('/roadmaps/generate', d),
  addNode: (id, d) => api.post(`/roadmaps/${id}/nodes`, d),
  updateNode: (rid, nid, d) => api.patch(`/roadmaps/${rid}/nodes/${nid}`, d),
  deleteNode: (rid, nid) => api.delete(`/roadmaps/${rid}/nodes/${nid}`),
  enroll: (id) => api.post(`/progress/roadmaps/${id}/enroll`),
  requestRoadmap: (title) => api.post('/roadmaps/request', { title }),
};

// Progress
export const progressApi = {
  getRoadmapProgress: (rid) => api.get(`/progress/roadmaps/${rid}`),
  updateNode: (rid, nid, d) => api.post(`/progress/roadmaps/${rid}/nodes/${nid}`, d),
  getNode: (rid, nid) => api.get(`/progress/roadmaps/${rid}/nodes/${nid}`),
};

// Chat
export const chatApi = {
  getSession: (nid, rid) => api.get(`/chat/sessions/${nid}`, { params: { roadmap_id: rid } }),
  getMessages: (nid, rid) => api.get(`/chat/sessions/${nid}/messages`, { params: { roadmap_id: rid } }),
  sendMessage: (nid, rid, d) => api.post(`/chat/sessions/${nid}/messages`, d, { params: { roadmap_id: rid } }),
  generateQuiz: (nid, rid) => api.post(`/chat/sessions/${nid}/quiz`, null, { params: { roadmap_id: rid } }),
  submitQuiz: (nid, rid, d) => api.post(`/chat/sessions/${nid}/quiz/submit`, d, { params: { roadmap_id: rid } }),
};

// Users
export const userApi = {
  me: () => api.get('/users/me'),
  update: (d) => api.patch('/users/me', d),
  leaderboard: () => api.get('/users/leaderboard'),
  transactions: () => api.get('/users/me/transactions'),
  list: (p) => api.get('/users', { params: p }),
};

// Admin
export const adminApi = {
  assign: (d) => api.post('/admin/assignments', d),
  getAssignments: (p) => api.get('/admin/assignments', { params: p }),
  updateAssignment: (id, d) => api.patch(`/admin/assignments/${id}`, d),
  deleteAssignment: (id) => api.delete(`/admin/assignments/${id}`),
  dashboard: () => api.get('/admin/analytics/dashboard'),
  skillGaps: (p) => api.get('/admin/analytics/skill-gaps', { params: p }),
  userAnalytics: (uid) => api.get(`/admin/analytics/users/${uid}`),
  getRoadmapRequests: () => api.get('/admin/roadmap-requests'),
  updateRoadmapRequest: (id, d) => api.patch(`/admin/roadmap-requests/${id}`, d),
};

// Resume
export const resumeApi = {
  upload: (formData) => api.post('/resume/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  list: () => api.get('/resume/me'),
};

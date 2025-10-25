import axios from "axios";

const API_BASE_URL = "/api";

// Create axios instance with default config
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

// Auth API functions
export const login = async (credentials) => {
  const response = await api.post("/auth/login", credentials);
  // Use 'token' instead of 'access_token'
  if (response.data.token) {
    localStorage.setItem("token", response.data.token);
  }
  return response.data;
};

export const logout = async () => {
  const response = await api.post("/auth/logout");
  return response.data;
};

export const register = async (userData) => {
  const response = await api.post("/auth/register", userData);
  return response.data;
};

export const checkUsernameAvailability = async (username) => {
  const response = await api.get(`/auth/check-username/${username}`);
  return response.data;
};

// Users API functions
export const getUsers = async () => {
  const response = await api.get("/admin/users");
  return response.data;
};

export const getUser = async (id) => {
  const response = await api.get(`/users/${id}`);
  return response.data;
};

// Lockers API functions
export const getLockers = async () => {
  const response = await api.get("/lockers");
  return response.data;
};

export const openLocker = async (lockerId) => {
  const response = await api.post(`/lockers/${lockerId}/open`);
  return response.data;
};

export const openFreeLocker = async () => {
  const response = await api.post("/lockers/open_free");
  return response.data;
};

export const closeLocker = async (lockerId) => {
  const response = await api.post(`/lockers/${lockerId}/close`);
  return response.data;
};

export const confirmPresence = async (lockerId, presenceData) => {
  const response = await api.post(`/lockers/${lockerId}/confirm_presence`, presenceData);
  return response.data;
};

export const reportMissingItem = async (lockerId, reportData) => {
  const response = await api.post(`/lockers/${lockerId}/report_missing`, reportData);
  return response.data;
}

export const getLockerStatus = async (lockerId) => {
  const response = await api.get(`/lockers/${lockerId}/status`);
  return response.data;
};

// Items API functions
export const getItems = async () => {
  const response = await api.get("/items");
  return response.data;
};

export const borrowItem = async (borrowData) => {
  const response = await api.post("/borrows", borrowData);
  return response.data;
};

export const returnItem = async (borrowId, returnData) => {
  const response = await api.post(`/borrows/${borrowId}/return`, returnData);
  return response.data;
};

export const confirmReturn = async (data) => {
  const response = await api.post(`/lockers/confirm_return`, data);
  return response.data;
};

// Logs API functions
export const getLogs = async () => {
  const response = await api.get("/logs");
  return response.data;
};

// Admin API functions
export const getStats = async () => {
  const response = await api.get("/admin/stats");
  return response.data;
};

export const getActiveBorrows = async () => {
  const response = await api.get("/admin/active-borrows");
  return response.data;
};

export const getRecentActivity = async () => {
  const response = await api.get("/admin/recent-activity");
  return response.data;
};

export const exportLogs = async () => {
  const response = await api.get("/admin/export/logs");
  return response.data;
};

export const exportUsers = async () => {
  const response = await api.get("/admin/export/users");
  return response.data;
};

export const exportBorrows = async () => {
  const response = await api.get("/admin/export/borrows");
  return response.data;
};

// User profile API functions
export const getUserProfile = async () => {
  const response = await api.get("/user/profile");
  return response.data;
};

export const getBorrows = async (params = {}) => {
  const response = await api.get("/borrows", { params });
  return response.data;
};

// Payments API functions
export const getPayments = async () => {
  const response = await api.get("/payments");
  return response.data;
};



export { api };
export default api;

/**
 * shared.js — 智慧养老云平台公共模块
 * Provides api() fetch wrapper, auth functions, and renderNavbar().
 */

var API_BASE = window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : '';

// ============================================================
// Auth helpers
// ============================================================

function getToken() {
    return localStorage.getItem('auth_token');
}

function isLoggedIn() {
    return !!getToken();
}

function logout() {
    localStorage.removeItem('auth_token');
    window.location.href = 'login.html';
}

async function validateToken() {
    const token = getToken();
    if (!token) return null;
    try {
        const res = await fetch(`${API_BASE}/api/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

async function getCurrentUser() {
    return await validateToken();
}

async function authFetch(url, options = {}) {
    const token = getToken();
    if (!token) {
        throw new Error('未登录');
    }
    const isFormData = options.body instanceof FormData;
    const headers = {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        'Authorization': `Bearer ${token}`,
        ...(options.headers || {})
    };
    const res = await fetch(`${API_BASE}${url}`, { ...options, headers });
    if (res.status === 401) {
        localStorage.removeItem('auth_token');
        throw new Error('登录已过期，请重新登录');
    }
    let data;
    try { data = await res.json(); } catch(e) { data = null; }
    if (!res.ok) {
        throw new Error((data && (data.error || data.detail)) || `请求失败 (${res.status})`);
    }
    return data;
}

// ============================================================
// General fetch wrapper (pre-existing)
// ============================================================

/**
 * Lightweight fetch wrapper that prepends API_BASE, sets JSON headers,
 * and parses the JSON response. Throws on non-OK status.
 */
async function api(url, options = {}) {
    const config = {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    };
    if (config.headers) {
        config.headers = { 'Content-Type': 'application/json', ...config.headers };
    }
    if (config.body && typeof config.body === 'object') {
        config.body = JSON.stringify(config.body);
    }
    const response = await fetch(`${API_BASE}${url}`, config);
    if (!response.ok) {
        const errText = await response.text();
        throw new Error(errText || `HTTP ${response.status}`);
    }
    return response.json();
}

/**
 * Renders the top navigation bar into #navbar.
 * Call once on DOMContentLoaded.
 */
function renderNavbar() {
    const container = document.getElementById('navbar');
    if (!container) return;

    const currentPage = window.location.pathname.split('/').pop() || 'index.html';

    container.innerHTML = `
        <header class="bg-white border-b border-slate-100 shadow-sm sticky top-0 z-40 py-4">
            <div class="max-w-7xl mx-auto px-4 flex flex-col md:flex-row justify-between items-center gap-3">
                <div class="flex items-center gap-3">
                    <span class="text-3xl text-blue-600">🏡</span>
                    <div>
                        <h1 class="font-bold text-xl tracking-wide text-slate-800" style="font-family: 'Noto Sans SC', 'Inter', sans-serif;">
                            孝心常在 · 智慧养老云平台
                        </h1>
                    </div>
                </div>
                <nav class="flex flex-wrap gap-2">
                    <a href="产品原型.html"
                       class="nav-btn text-sm px-4 py-2 rounded-lg font-medium transition-all duration-200 ${currentPage === '产品原型.html' || currentPage === '' || currentPage === 'index.html' ? 'bg-blue-600 text-white shadow-md' : 'bg-slate-100 hover:bg-slate-200 text-slate-600'}">
                        <i class="fa-solid fa-house mr-1.5"></i>首页入口
                    </a>
                    <a href="institutions.html"
                       class="nav-btn text-sm px-4 py-2 rounded-lg font-medium transition-all duration-200 ${currentPage === 'institutions.html' ? 'bg-blue-600 text-white shadow-md' : 'bg-slate-100 hover:bg-slate-200 text-slate-600'}">
                        <i class="fa-solid fa-building-columns mr-1.5"></i>机构养老查询
                    </a>
                </nav>
            </div>
        </header>
    `;
}

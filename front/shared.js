/**
 * shared.js — 智慧养老云平台公共模块
 *
 * 提供：
 * - API_BASE          后端地址（localhost 自动指向 8000 端口）
 * - api()             通用 fetch 封装（JSON 请求/响应）
 * - authFetch()       带认证的 fetch 封装
 * - getToken() / isLoggedIn() / logout()
 * - escapeHtml()      XSS 防护
 * - toISODate()       Date → "YYYY-MM-DD"
 * - showToast()       全局轻提示
 * - renderNavbar()    统一顶部导航栏
 */

// ============================================================
// 后端地址
// ============================================================

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
    window.location.href = 'index.html';
}

/**
 * 带 Bearer token 的 fetch 封装。
 * 自动处理 JSON / FormData，401 时清除 token 并抛错。
 */
async function authFetch(url, options) {
    options = options || {};
    var token = getToken();
    if (!token) throw new Error('未登录');

    var isFormData = options.body instanceof FormData;
    var headers = {};
    if (!isFormData) headers['Content-Type'] = 'application/json';
    headers['Authorization'] = 'Bearer ' + token;
    // 合并调用方自定义 headers
    if (options.headers) {
        for (var k in options.headers) headers[k] = options.headers[k];
    }

    var res = await fetch(API_BASE + url, Object.assign({}, options, { headers: headers }));
    if (res.status === 401) {
        localStorage.removeItem('auth_token');
        throw new Error('登录已过期，请重新登录');
    }

    var data;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
        throw new Error((data && (data.error || data.detail)) || ('请求失败 (' + res.status + ')'));
    }
    return data;
}

// ============================================================
// 通用 fetch 封装（无需认证的场景）
// ============================================================

/**
 * 轻量 JSON fetch：自动拼接 API_BASE，设置 JSON headers，解析响应。
 */
async function api(url, options) {
    options = options || {};
    var headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    var config = Object.assign({}, options, { headers: headers });

    if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData)) {
        config.body = JSON.stringify(config.body);
    }

    var response = await fetch(API_BASE + url, config);
    if (!response.ok) {
        var errText = await response.text();
        throw new Error(errText || ('HTTP ' + response.status));
    }
    return response.json();
}

// ============================================================
// 工具函数
// ============================================================

/** HTML 转义，防止 XSS */
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/** Date 对象 → "YYYY-MM-DD" 字符串 */
function toISODate(date) {
    var y = date.getFullYear();
    var m = String(date.getMonth() + 1).padStart(2, '0');
    var d = String(date.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + d;
}

// ============================================================
// Toast 轻提示（全局单例）
// ============================================================

var _toastEl = null;
var _toastTimer = null;

function showToast(message) {
    if (!_toastEl) {
        _toastEl = document.createElement('div');
        _toastEl.className = 'toast';
        _toastEl.style.display = 'none';
        document.body.appendChild(_toastEl);
    }
    _toastEl.textContent = message;
    _toastEl.style.display = 'block';
    _toastEl.style.opacity = '1';
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(function () {
        _toastEl.style.opacity = '0';
        setTimeout(function () { _toastEl.style.display = 'none'; }, 300);
    }, 3000);
}

// ============================================================
// 统一导航栏
// ============================================================

/**
 * 渲染统一导航栏到 #navbar 元素。
 * @param {string} [activePage]  当前页面标识（高亮用），不传则自动检测
 */
function renderNavbar(activePage) {
    var container = document.getElementById('navbar');
    if (!container) return;

    var currentPage = activePage || window.location.pathname.split('/').pop() || 'index.html';

    var links = [
        { href: 'index.html',        label: '首页',     icon: 'fa-house',            key: 'index.html' },
        { href: 'policy.html',       label: '政策查询', icon: 'fa-file-invoice-dollar', key: 'policy.html' },
        { href: 'institutions.html', label: '机构查询', icon: 'fa-building-columns', key: 'institutions.html' },
        { href: 'services.html',     label: '居家服务', icon: 'fa-hand-holding-heart', key: 'services.html' },
        { href: 'health.html',       label: '健康科普', icon: 'fa-heart-pulse',      key: 'health.html' },
        { href: 'ai-assistant.html', label: 'AI助手',   icon: 'fa-robot',            key: 'ai-assistant.html' },
    ];

    // 产品原型.html 归入"首页入口"高亮
    if (currentPage === '产品原型.html') currentPage = 'index.html';

    var navHtml = '';
    links.forEach(function (link) {
        var isActive = currentPage === link.key;
        var cls = isActive
            ? 'text-warm-700 bg-warm-50 font-semibold'
            : 'text-slate-500 hover:text-warm-700 hover:bg-warm-50';
        navHtml += '<a href="' + link.href + '"'
            + ' class="text-sm px-3 py-1.5 rounded-lg transition-colors ' + cls + '">'
            + '<i class="fa-solid ' + link.icon + ' mr-1"></i>' + link.label
            + '</a>';
    });

    // 右侧：登录状态
    var rightHtml = '';
    if (isLoggedIn()) {
        rightHtml = '<a href="产品原型.html" class="text-sm px-3 py-1.5 rounded-lg text-warm-600 hover:text-warm-800 hover:bg-warm-50 transition-colors">'
            + '<i class="fa-solid fa-user mr-1"></i>用户中心</a>';
    } else {
        rightHtml = '<a href="产品原型.html" class="text-sm px-4 py-1.5 rounded-lg bg-warm-600 text-white hover:bg-warm-700 transition-colors font-medium">登录</a>';
    }

    container.innerHTML =
        '<nav class="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-slate-100 shadow-sm">'
        + '<div class="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">'
        +   '<div class="flex items-center gap-2.5">'
        +     '<span class="text-2xl">🏡</span>'
        +     '<span class="text-lg font-bold text-warm-700 tracking-wide">孝心常在 · 智慧养老</span>'
        +   '</div>'
        +   '<div class="hidden md:flex items-center gap-1">' + navHtml + '</div>'
        +   '<div class="flex items-center gap-2">' + rightHtml + '</div>'
        + '</div>'
        + '<!-- 移动端导航 -->'
        + '<div class="md:hidden flex items-center gap-1 px-4 pb-2 overflow-x-auto no-scrollbar">' + navHtml + '</div>'
        + '</nav>';
}

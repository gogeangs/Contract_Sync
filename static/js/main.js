// ============================================================
// Contract Sync v2 — Frontend Main JS
// ============================================================

// ============ 유틸리티 함수 ============

window.confirmDialog = function(message, { title = '확인', confirmText = '확인', cancelText = '취소', danger = false } = {}) {
    return new Promise((resolve) => {
        const backdrop = document.createElement('div');
        backdrop.className = 'fixed inset-0 z-[110] flex items-center justify-center bg-black bg-opacity-50 confirm-backdrop';
        backdrop.innerHTML = `
            <div class="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-sm mx-4 p-6 transform transition-all">
                <h3 class="confirm-title text-lg font-semibold text-gray-800 dark:text-gray-100 mb-2"></h3>
                <p class="confirm-message text-sm text-gray-600 dark:text-gray-300 mb-6"></p>
                <div class="flex justify-end gap-3">
                    <button class="confirm-cancel px-4 py-2 text-sm text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"></button>
                    <button class="confirm-ok px-4 py-2 text-sm text-white rounded-lg transition-colors ${danger ? 'bg-red-600 hover:bg-red-700' : 'bg-indigo-600 hover:bg-indigo-700'}"></button>
                </div>
            </div>
        `;
        backdrop.querySelector('.confirm-title').textContent = title;
        backdrop.querySelector('.confirm-message').textContent = message;
        backdrop.querySelector('.confirm-cancel').textContent = cancelText;
        backdrop.querySelector('.confirm-ok').textContent = confirmText;
        document.body.appendChild(backdrop);
        backdrop.querySelector('.confirm-cancel').addEventListener('click', () => { backdrop.remove(); resolve(false); });
        backdrop.querySelector('.confirm-ok').addEventListener('click', () => { backdrop.remove(); resolve(true); });
        backdrop.addEventListener('click', (e) => { if (e.target === backdrop) { backdrop.remove(); resolve(false); } });
        const escHandler = (e) => { if (e.key === 'Escape') { document.removeEventListener('keydown', escHandler); backdrop.remove(); resolve(false); } };
        document.addEventListener('keydown', escHandler);
    });
};

function debounce(fn, delay = 300) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

window.formatRelativeTime = function(isoStr) {
    if (!isoStr) return '';
    const diff = Date.now() - new Date(isoStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return '방금 전';
    if (mins < 60) return `${mins}분 전`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}시간 전`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}일 전`;
    return new Date(isoStr).toLocaleDateString('ko-KR');
};

window.getFileIcon = function(filename) {
    if (!filename) return '📄';
    const ext = filename.split('.').pop().toLowerCase();
    const map = { pdf: '📕', doc: '📘', docx: '📘', hwp: '📗', hwpx: '📗', xls: '📊', xlsx: '📊', csv: '📊', ppt: '📙', pptx: '📙', jpg: '🖼️', jpeg: '🖼️', png: '🖼️', gif: '🖼️', zip: '📦', rar: '📦', txt: '📝' };
    return map[ext] || '📄';
};

window.renderComment = function(content) {
    if (!content) return '';
    const escaped = content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return escaped.replace(/@\[([^\]]+)\]\([^)]+\)/g, '<span class="text-indigo-600 font-medium">@$1</span>')
        .replace(/(?<!\()@([\w.+-]+@[\w-]+\.[\w.-]+)/g, '<span class="text-indigo-600 font-medium">@$1</span>');
};

// ============ 검색형 드롭다운 ============

window.searchDropdown = function(cfg) {
    return {
        _cfg: cfg,
        open: false,
        query: '',
        items: [],
        selectedId: cfg.modelValue || '',
        selectedLabel: cfg.initialLabel || '',
        loading: false,

        get displayText() {
            return this.selectedLabel || this._cfg.placeholder || '선택하세요';
        },

        async search(q) {
            this.loading = true;
            try {
                const url = `${this._cfg.endpoint}?search=${encodeURIComponent(q || '')}&page=1&size=20`;
                const data = await api.get(url);
                this.items = data?.[this._cfg.listKey] || [];
            } catch { this.items = []; }
            this.loading = false;
        },

        doSearch: debounce(function() { this.search(this.query); }, 300),

        select(item) {
            this.selectedId = item[this._cfg.valueKey];
            this.selectedLabel = item[this._cfg.labelKey];
            this.open = false;
            this.query = '';
            this._cfg.onSelect?.(item);
        },

        clear() {
            this.selectedId = '';
            this.selectedLabel = '';
            this.query = '';
            const empty = {};
            empty[this._cfg.valueKey] = '';
            this._cfg.onSelect?.(empty);
        },

        async init() {
            if (this.selectedId && !this.selectedLabel) {
                await this.search('');
                const found = this.items.find(i => String(i[this._cfg.valueKey]) === String(this.selectedId));
                if (found) this.selectedLabel = found[this._cfg.labelKey];
            }
        },
    };
};

// ============ 공통 헬퍼 ============

window.CS = {
    statusLabel: { pending: '대기', in_progress: '진행중', completed: '완료', report_sent: '보고 발송', feedback_pending: '피드백 대기', confirmed: '확인됨', revision_requested: '수정 요청', planning: '기획중', active: '진행중', on_hold: '보류', cancelled: '취소' },
    statusClass: { pending: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400', in_progress: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400', completed: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', report_sent: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400', feedback_pending: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400', confirmed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400', revision_requested: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400', planning: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400', active: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400', on_hold: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400', cancelled: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
    priorityClass: { '긴급': 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400', '높음': 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400', '보통': 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400', '낮음': 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400' },
    typeLabel: { outsourcing: '외주', internal: '내부', maintenance: '유지보수' },
    typeClass: { outsourcing: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400', internal: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', maintenance: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' },

    formatDate(str) {
        if (!str) return '-';
        try { return new Date(str).toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' }); } catch { return str; }
    },

    getDday(dateStr) {
        if (!dateStr) return null;
        const due = new Date(dateStr + 'T00:00:00');
        if (isNaN(due.getTime())) return null;
        const today = new Date(); today.setHours(0,0,0,0);
        return Math.ceil((due - today) / 86400000);
    },

    getDdayLabel(dateStr) {
        const d = this.getDday(dateStr);
        if (d === null) return '';
        if (d < 0) return `D+${Math.abs(d)}`;
        if (d === 0) return 'D-Day';
        return `D-${d}`;
    },

    getDdayClass(dateStr) {
        const d = this.getDday(dateStr);
        if (d === null) return '';
        if (d < 0) return 'bg-red-600 text-white';
        if (d === 0) return 'bg-red-500 text-white';
        if (d <= 3) return 'bg-red-100 text-red-700';
        if (d <= 7) return 'bg-orange-100 text-orange-700';
        return 'bg-gray-100 text-gray-600';
    },

    progress(total, completed) {
        if (!total || total === 0) return 0;
        return Math.round((completed / total) * 100);
    },
};

// ============ API 헬퍼 ============

const api = {
    async _fetch(method, url, body) {
        const opts = { method, headers: {} };
        if (body && !(body instanceof FormData)) {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(body);
        } else if (body) {
            opts.body = body;
        }
        const res = await fetch('/api/v1' + url, opts);
        if (res.status === 204) return null;
        const data = await res.json().catch(() => null);
        if (!res.ok) {
            const msg = data?.detail || `요청 실패 (${res.status})`;
            throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
        }
        return data;
    },
    get(url) { return this._fetch('GET', url); },
    post(url, body) { return this._fetch('POST', url, body); },
    put(url, body) { return this._fetch('PUT', url, body); },
    patch(url, body) { return this._fetch('PATCH', url, body); },
    del(url) { return this._fetch('DELETE', url); },
};

// ============ Toast 시스템 ============

function toastManager() {
    return {
        toasts: [], _id: 0,
        show(message, type = 'info', duration = 3000) {
            const id = ++this._id;
            this.toasts.push({ id, message, type, visible: true });
            setTimeout(() => this.dismiss(id), duration);
        },
        success(msg) { this.show(msg, 'success', 3000); },
        error(msg) { this.show(msg, 'error', 5000); },
        warning(msg) { this.show(msg, 'warning', 4000); },
        info(msg) { this.show(msg, 'info', 3000); },
        dismiss(id) {
            const t = this.toasts.find(t => t.id === id);
            if (t) t.visible = false;
            setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 300);
        }
    };
}

window._toast = { _queue: [], ready: false };
window.toast = {
    success(msg) { window._toast.ready ? window.dispatchEvent(new CustomEvent('toast', { detail: { message: msg, type: 'success' } })) : window._toast._queue.push({ message: msg, type: 'success' }); },
    error(msg) { window._toast.ready ? window.dispatchEvent(new CustomEvent('toast', { detail: { message: msg, type: 'error' } })) : window._toast._queue.push({ message: msg, type: 'error' }); },
    warning(msg) { window._toast.ready ? window.dispatchEvent(new CustomEvent('toast', { detail: { message: msg, type: 'warning' } })) : window._toast._queue.push({ message: msg, type: 'warning' }); },
    info(msg) { window._toast.ready ? window.dispatchEvent(new CustomEvent('toast', { detail: { message: msg, type: 'info' } })) : window._toast._queue.push({ message: msg, type: 'info' }); },
};

// ============================================================
// App Shell — 인증 + 라우팅 + 사이드바
// ============================================================

function appShell() {
    return {
        // 인증
        user: null, teams: [], loading: true,
        showModal: false, modalMode: 'login',
        email: '', password: '', passwordConfirm: '', verificationCode: '',
        formLoading: false, formError: '', formSuccess: '', emailVerified: false,
        showPassword: false, showPasswordConfirm: false,

        // 라우팅
        currentPage: 'dashboard',
        pageParams: {},

        // 사이드바
        sidebarOpen: false,

        // 다크 모드
        darkMode: false,

        // 알림
        notifications: [], unreadCount: 0, showNotifPanel: false, notifLoading: false, notifFilter: 'all',

        // 팀
        selectedTeamId: null,
        teamDropdown: false,

        // 프로필 드롭다운
        profileDropdown: false,

        async init() {
            this.initDarkMode();
            await this.checkAuth();
            this.initRouter();
        },

        // ---- 라우터 ----
        initRouter() {
            this.handleRoute();
            window.addEventListener('hashchange', () => this.handleRoute());
        },

        handleRoute() {
            const hash = window.location.hash || '#/dashboard';
            const path = hash.substring(1).split('?')[0];
            let m;

            if (path === '/' || path === '/dashboard') {
                this.currentPage = 'dashboard'; this.pageParams = {};
            } else if (path === '/clients') {
                this.currentPage = 'clients'; this.pageParams = {};
            } else if ((m = path.match(/^\/clients\/(\d+)$/))) {
                this.currentPage = 'clientDetail'; this.pageParams = { id: parseInt(m[1]) };
            } else if (path === '/projects') {
                this.currentPage = 'projects'; this.pageParams = {};
            } else if ((m = path.match(/^\/projects\/(\d+)$/))) {
                this.currentPage = 'projectDetail'; this.pageParams = { id: parseInt(m[1]) };
            } else if (path === '/tasks') {
                this.currentPage = 'tasks'; this.pageParams = {};
            } else if ((m = path.match(/^\/projects\/(\d+)\/documents\/upload$/))) {
                this.currentPage = 'documentUpload'; this.pageParams = { projectId: parseInt(m[1]) };
            } else if ((m = path.match(/^\/documents\/(\d+)$/))) {
                this.currentPage = 'documentDetail'; this.pageParams = { id: parseInt(m[1]) };
            } else if ((m = path.match(/^\/documents\/(\d+)\/estimate$/))) {
                this.currentPage = 'estimateSheets'; this.pageParams = { id: parseInt(m[1]) };
            } else if ((m = path.match(/^\/tasks\/(\d+)\/completion-report$/))) {
                this.currentPage = 'completionReport'; this.pageParams = { taskId: parseInt(m[1]) };
            } else if ((m = path.match(/^\/feedback\/([a-zA-Z0-9_-]+)$/))) {
                this.currentPage = 'feedback'; this.pageParams = { token: m[1] };
            } else if (path === '/reports') {
                this.currentPage = 'reports'; this.pageParams = {};
            } else if ((m = path.match(/^\/reports\/(\d+)$/))) {
                this.currentPage = 'reportEditor'; this.pageParams = { id: parseInt(m[1]) };
            } else if (path === '/payments') {
                this.currentPage = 'payments'; this.pageParams = {};
            } else if (path === '/estimate') {
                this.currentPage = 'estimate'; this.pageParams = {};
            } else if (path === '/templates') {
                this.currentPage = 'templates'; this.pageParams = {};
            } else if ((m = path.match(/^\/portal\/([a-zA-Z0-9_-]+)$/))) {
                this.currentPage = 'portal'; this.pageParams = { token: m[1] };
            } else if (path === '/settings') {
                this.currentPage = 'settings'; this.pageParams = {};
            } else {
                this.currentPage = 'dashboard'; this.pageParams = {};
            }

            this.sidebarOpen = false;
            window.dispatchEvent(new CustomEvent('route-changed', { detail: { page: this.currentPage, params: this.pageParams } }));
        },

        navigate(path) {
            window.location.hash = path;
        },

        get selectedTeamLabel() {
            if (!this.selectedTeamId) return '개인';
            const t = this.teams.find(t => t.id === this.selectedTeamId || t.team_id === this.selectedTeamId);
            return t?.name || '팀';
        },

        // ---- 다크 모드 ----
        initDarkMode() {
            const saved = localStorage.getItem('darkMode');
            this.darkMode = saved !== null ? saved === 'true' : window.matchMedia('(prefers-color-scheme: dark)').matches;
            this.applyDarkMode();
        },
        toggleDarkMode() {
            this.darkMode = !this.darkMode;
            localStorage.setItem('darkMode', this.darkMode);
            this.applyDarkMode();
        },
        applyDarkMode() {
            document.documentElement.classList.toggle('dark', this.darkMode);
        },

        // ---- 인증 ----
        async checkAuth() {
            try {
                const res = await fetch('/api/v1/auth/me');
                const data = await res.json();
                if (data.logged_in && data.user) {
                    this.user = data.user;
                    this.teams = data.teams || [];
                    window._teams = this.teams;
                    window._selectedTeamId = this.selectedTeamId;
                    this.loadUnreadCount();
                    if (!this._notifInterval) {
                        this._notifInterval = setInterval(() => { if (!document.hidden) this.loadUnreadCount(); }, 30000);
                    }
                }
            } catch { /* ignore */ }
            finally { this.loading = false; }
        },

        openLogin() { this.resetForm(); this.modalMode = 'login'; this.showModal = true; },
        openSignup() { this.resetForm(); this.modalMode = 'signup'; this.showModal = true; },
        closeModal() { this.showModal = false; this.resetForm(); },
        resetForm() { this.email = ''; this.password = ''; this.passwordConfirm = ''; this.verificationCode = ''; this.formError = ''; this.formSuccess = ''; this.emailVerified = false; },

        async sendVerificationCode() {
            if (!this.email) { this.formError = '이메일을 입력해주세요.'; return; }
            this.formLoading = true; this.formError = '';
            try {
                const res = await fetch('/api/v1/auth/send-code', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ email: this.email }) });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || '인증코드 발송 실패');
                if (data.dev_code) { this.verificationCode = data.dev_code; this.formSuccess = data.message; }
                else { this.formSuccess = '인증코드가 발송되었습니다.'; }
                this.modalMode = 'verify';
            } catch (e) { this.formError = e.message; }
            finally { this.formLoading = false; }
        },

        async verifyCode() {
            if (!this.verificationCode) { this.formError = '인증코드를 입력해주세요.'; return; }
            this.formLoading = true; this.formError = '';
            try {
                const res = await fetch('/api/v1/auth/verify-code', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ email: this.email, code: this.verificationCode }) });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || '인증 실패');
                this.emailVerified = true; this.formSuccess = '이메일 인증 완료! 비밀번호를 설정해주세요.'; this.modalMode = 'signup';
            } catch (e) { this.formError = e.message; }
            finally { this.formLoading = false; }
        },

        async signup() {
            if (!this.emailVerified) { this.formError = '이메일 인증이 필요합니다.'; return; }
            if (!this.password || !this.passwordConfirm) { this.formError = '비밀번호를 입력해주세요.'; return; }
            if (this.password !== this.passwordConfirm) { this.formError = '비밀번호가 일치하지 않습니다.'; return; }
            if (this.password.length < 8) { this.formError = '비밀번호는 8자 이상이어야 합니다.'; return; }
            if (!/[A-Za-z]/.test(this.password) || !/\d/.test(this.password)) { this.formError = '비밀번호는 영문자와 숫자를 모두 포함해야 합니다.'; return; }
            this.formLoading = true; this.formError = '';
            try {
                const res = await fetch('/api/v1/auth/signup', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ email: this.email, password: this.password, password_confirm: this.passwordConfirm }) });
                if (!res.ok) { let msg = '회원가입 실패'; try { const d = await res.json(); msg = d.detail || msg; } catch { msg = `서버 오류 (${res.status})`; } throw new Error(msg); }
                this.closeModal(); await this.checkAuth();
            } catch (e) { this.formError = e.message; }
            finally { this.formLoading = false; }
        },

        async login() {
            if (!this.email || !this.password) { this.formError = '이메일과 비밀번호를 입력해주세요.'; return; }
            this.formLoading = true; this.formError = '';
            try {
                const res = await fetch('/api/v1/auth/login/email', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ email: this.email, password: this.password }) });
                if (!res.ok) { let msg = '로그인 실패'; try { const d = await res.json(); msg = d.detail || msg; } catch { msg = `서버 오류 (${res.status})`; } throw new Error(msg); }
                this.closeModal(); await this.checkAuth();
            } catch (e) { this.formError = e.message; }
            finally { this.formLoading = false; }
        },

        async logout() {
            try {
                await fetch('/api/v1/auth/logout', { method: 'POST' });
                this.user = null; this.teams = []; this.notifications = []; this.unreadCount = 0;
                if (this._notifInterval) { clearInterval(this._notifInterval); this._notifInterval = null; }
                this.navigate('/dashboard');
            } catch { window.toast.error('로그아웃 실패'); }
        },

        get passwordStrength() {
            const p = this.password;
            if (!p) return { score: 0, label: '', color: 'bg-gray-200', width: '0%' };
            let s = 0;
            if (p.length >= 8) s++; if (p.length >= 12) s++;
            if (/[A-Z]/.test(p)) s++; if (/[a-z]/.test(p)) s++;
            if (/\d/.test(p)) s++; if (/[!@#$%^&*(),.?":{}|<>]/.test(p)) s++;
            if (s <= 2) return { score: s, label: '약함', color: 'bg-red-500', width: '33%' };
            if (s <= 4) return { score: s, label: '보통', color: 'bg-yellow-500', width: '66%' };
            return { score: s, label: '강함', color: 'bg-green-500', width: '100%' };
        },

        // ---- 알림 ----
        async loadUnreadCount() {
            try { const r = await fetch('/api/v1/notifications/unread-count'); if (r.ok) { this.unreadCount = (await r.json()).unread_count; } } catch {}
        },
        async loadNotifications() {
            this.notifLoading = true;
            try { const r = await fetch('/api/v1/notifications?size=20'); if (r.ok) { const d = await r.json(); this.notifications = d.items || []; this.unreadCount = d.unread_count; } } catch {}
            finally { this.notifLoading = false; }
        },
        toggleNotifications() { this.showNotifPanel = !this.showNotifPanel; if (this.showNotifPanel) this.loadNotifications(); },
        async markNotifRead(id) {
            try { const r = await fetch(`/api/v1/notifications/${id}/read`, { method: 'PATCH' }); if (r.ok) { const n = this.notifications.find(x => x.id === id); if (n && !n.is_read) { n.is_read = true; this.unreadCount = Math.max(0, this.unreadCount - 1); } } } catch {}
        },
        async markAllNotifRead() {
            try { const r = await fetch('/api/v1/notifications/read-all', { method: 'PATCH' }); if (r.ok) { this.notifications.forEach(n => n.is_read = true); this.unreadCount = 0; } } catch {}
        },
        get filteredNotifications() {
            if (this.notifFilter === 'all') return this.notifications;
            return this.notifications.filter(n => n.type === this.notifFilter);
        },

        // ---- 팀 ----
        switchTeam(teamId) {
            this.selectedTeamId = teamId || null;
            this.teamDropdown = false;
            window._selectedTeamId = this.selectedTeamId;
            window.dispatchEvent(new CustomEvent('team-switched', { detail: this.selectedTeamId }));
        },
    };
}

// ============================================================
// 대시보드 페이지
// ============================================================

function dashboardPage() {
    return {
        loading: true,
        stats: { projects: 0, pendingTasks: 0, inProgressTasks: 0, completedTasks: 0 },
        recentTasks: [],
        recentProjects: [],

        async init() {
            await this.load();
            this.$el.addEventListener('route-changed', () => { if (this.$data.currentPage === 'dashboard') this.load(); });
        },

        async load() {
            if (!document.cookie.includes('session_token')) { this.loading = false; return; }
            this.loading = true;
            try {
                const [pData, tData, pending, inProg, done] = await Promise.all([
                    api.get('/projects?page=1&size=5'),
                    api.get('/tasks?page=1&size=10'),
                    api.get('/tasks?page=1&size=1&status=pending'),
                    api.get('/tasks?page=1&size=1&status=in_progress'),
                    api.get('/tasks?page=1&size=1&status=completed'),
                ]);
                this.recentProjects = pData?.projects || [];
                this.recentTasks = tData?.tasks || [];
                this.stats.projects = pData?.total || 0;
                this.stats.pendingTasks = pending?.total || 0;
                this.stats.inProgressTasks = inProg?.total || 0;
                this.stats.completedTasks = done?.total || 0;
            } catch (e) { window.toast.error('대시보드 로드 실패'); }
            finally { this.loading = false; }
        },
    };
}

// ============================================================
// 발주처 목록 페이지
// ============================================================

function clientListPage() {
    return {
        clients: [], total: 0, loading: true,
        search: '', categoryFilter: '',
        page: 1, size: 20,
        showCreateModal: false, showDeleteModal: false,
        deleteTarget: null, saving: false,
        form: { name: '', contact_name: '', contact_email: '', contact_phone: '', address: '', category: '', memo: '' },
        editMode: false, editId: null,

        async init() {
            await this.loadClients();
        },

        async loadClients() {
            this.loading = true;
            try {
                let url = `/clients?page=${this.page}&size=${this.size}`;
                if (this.search) url += `&search=${encodeURIComponent(this.search)}`;
                if (this.categoryFilter) url += `&category=${encodeURIComponent(this.categoryFilter)}`;
                const data = await api.get(url);
                this.clients = data?.clients || [];
                this.total = data?.total || 0;
            } catch (e) { window.toast.error('발주처 목록 로드 실패'); }
            finally { this.loading = false; }
        },

        openCreate() {
            this.form = { name: '', contact_name: '', contact_email: '', contact_phone: '', address: '', category: '', memo: '' };
            this.editMode = false; this.editId = null; this.showCreateModal = true;
        },

        openEdit(client) {
            this.form = { name: client.name, contact_name: client.contact_name || '', contact_email: client.contact_email || '', contact_phone: client.contact_phone || '', address: client.address || '', category: client.category || '', memo: client.memo || '' };
            this.editMode = true; this.editId = client.id; this.showCreateModal = true;
        },

        async save() {
            if (!this.form.name.trim()) { window.toast.warning('발주처명을 입력해주세요.'); return; }
            this.saving = true;
            try {
                const body = { ...this.form };
                if (!body.contact_email) body.contact_email = null;
                if (this.editMode) {
                    await api.put(`/clients/${this.editId}`, body);
                    window.toast.success('발주처가 수정되었습니다.');
                } else {
                    await api.post('/clients', body);
                    window.toast.success('발주처가 등록되었습니다.');
                }
                this.showCreateModal = false;
                await this.loadClients();
            } catch (e) { window.toast.error(e.message); }
            finally { this.saving = false; }
        },

        confirmDelete(client) { this.deleteTarget = client; this.showDeleteModal = true; },

        async deleteClient() {
            if (!this.deleteTarget) return;
            try {
                await api.del(`/clients/${this.deleteTarget.id}`);
                window.toast.success('발주처가 삭제되었습니다.');
                this.showDeleteModal = false; this.deleteTarget = null;
                await this.loadClients();
            } catch (e) { window.toast.error(e.message); }
        },

        doSearch: debounce(function() { this.page = 1; this.loadClients(); }, 300),

        get totalPages() { return Math.ceil(this.total / this.size) || 1; },

        goPage(p) { if (p >= 1 && p <= this.totalPages) { this.page = p; this.loadClients(); } },
    };
}

// ============================================================
// 발주처 상세 페이지
// ============================================================

function clientDetailPage() {
    return {
        client: null, projects: [], loading: true,
        detailTab: 'projects',
        showEditModal: false, saving: false,
        form: {},

        async init() {
            const id = this._getRouteId();
            if (id) await this.load(id);
        },

        _getRouteId() {
            const hash = window.location.hash || '';
            const m = hash.match(/^#\/clients\/(\d+)$/);
            return m ? parseInt(m[1]) : null;
        },

        async load(id) {
            this.loading = true;
            try {
                const [client, pData] = await Promise.all([
                    api.get(`/clients/${id}`),
                    api.get(`/clients/${id}/projects`),
                ]);
                this.client = client;
                this.projects = pData?.projects || pData || [];
            } catch (e) { window.toast.error('발주처 정보를 불러올 수 없습니다.'); }
            finally { this.loading = false; }
        },

        openEdit() {
            if (!this.client) return;
            this.form = { name: this.client.name, contact_name: this.client.contact_name || '', contact_email: this.client.contact_email || '', contact_phone: this.client.contact_phone || '', address: this.client.address || '', category: this.client.category || '', memo: this.client.memo || '' };
            this.showEditModal = true;
        },

        async saveEdit() {
            if (!this.form.name?.trim()) { window.toast.warning('발주처명을 입력해주세요.'); return; }
            this.saving = true;
            try {
                const body = { ...this.form };
                if (!body.contact_email) body.contact_email = null;
                this.client = await api.put(`/clients/${this.client.id}`, body);
                window.toast.success('발주처 정보가 수정되었습니다.');
                this.showEditModal = false;
            } catch (e) { window.toast.error(e.message); }
            finally { this.saving = false; }
        },

        async deleteClient() {
            if (!await window.confirmDialog('이 발주처를 삭제하시겠습니까?', { title: '발주처 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/clients/${this.client.id}`);
                window.toast.success('발주처가 삭제되었습니다.');
                window.location.hash = '#/clients';
            } catch (e) { window.toast.error(e.message); }
        },
    };
}

// ============================================================
// 프로젝트 목록 페이지
// ============================================================

function projectListPage() {
    return {
        projects: [], total: 0, loading: true,
        search: '', filterType: '', filterStatus: '',
        page: 1, size: 20,
        showCreateModal: false, saving: false,
        form: { project_name: '', project_type: 'outsourcing', client_id: '', description: '', start_date: '', end_date: '', contract_amount: '' },

        async init() {
            await this.loadProjects();
        },

        async loadProjects() {
            this.loading = true;
            try {
                let url = `/projects?page=${this.page}&size=${this.size}`;
                if (this.search) url += `&search=${encodeURIComponent(this.search)}`;
                if (this.filterType) url += `&type=${this.filterType}`;
                if (this.filterStatus) url += `&status=${this.filterStatus}`;
                const data = await api.get(url);
                this.projects = data?.projects || [];
                this.total = data?.total || 0;
            } catch (e) { window.toast.error('프로젝트 목록 로드 실패'); }
            finally { this.loading = false; }
        },

        openCreate() {
            this.form = { project_name: '', project_type: 'outsourcing', client_id: '', description: '', start_date: '', end_date: '', contract_amount: '' };
            this.showCreateModal = true;
        },

        async save() {
            if (!this.form.project_name.trim()) { window.toast.warning('프로젝트명을 입력해주세요.'); return; }
            if (this.form.project_type === 'outsourcing' && !this.form.client_id) { window.toast.warning('외주 프로젝트는 발주처를 선택해주세요.'); return; }
            this.saving = true;
            try {
                const body = { ...this.form };
                body.client_id = body.client_id ? parseInt(body.client_id) : null;
                if (!body.contract_amount) body.contract_amount = null;
                await api.post('/projects', body);
                window.toast.success('프로젝트가 생성되었습니다.');
                this.showCreateModal = false;
                await this.loadProjects();
            } catch (e) { window.toast.error(e.message); }
            finally { this.saving = false; }
        },

        doSearch: debounce(function() { this.page = 1; this.loadProjects(); }, 300),

        get totalPages() { return Math.ceil(this.total / this.size) || 1; },
        goPage(p) { if (p >= 1 && p <= this.totalPages) { this.page = p; this.loadProjects(); } },
    };
}

// ============================================================
// 프로젝트 상세 페이지
// ============================================================

function projectDetailPage() {
    return {
        project: null, tasks: [], documents: [], loading: true,
        activeTab: 'tasks',
        showEditModal: false, saving: false,
        showTaskModal: false, taskSaving: false,
        showTaskDetailModal: false, selectedTask: null,
        portalToken: null, portalLoading: false, showPortalModal: false,
        form: {},
        taskForm: { task_name: '', phase: '', priority: '보통', due_date: '', start_date: '', assignee_id: '', is_client_facing: false, description: '' },

        async init() {
            const id = this._getRouteId();
            if (id) {
                await this.load(id);
            }
        },

        _getRouteId() {
            const m = (window.location.hash || '').match(/^#\/projects\/(\d+)$/);
            return m ? parseInt(m[1]) : null;
        },

        async load(id) {
            this.loading = true;
            try {
                const [project, tData] = await Promise.all([
                    api.get(`/projects/${id}`),
                    api.get(`/tasks?project_id=${id}&page=1&size=100`),
                ]);
                this.project = project;
                this.tasks = tData?.tasks || [];
            } catch (e) { window.toast.error('프로젝트를 불러올 수 없습니다.'); }
            finally { this.loading = false; }
        },

        async loadDocuments() {
            if (!this.project) return;
            try {
                const res = await api.get(`/projects/${this.project.id}/documents`);
                this.documents = res?.documents || res || [];
            } catch (e) { this.documents = []; }
        },

        get progress() {
            if (!this.project) return 0;
            return CS.progress(this.project.task_count || this.tasks.length, this.project.completed_task_count || this.tasks.filter(t => t.status === 'completed' || t.status === 'confirmed').length);
        },

        // 업무 생성
        openTaskCreate() {
            this.taskForm = { task_name: '', phase: '', priority: '보통', due_date: '', start_date: '', assignee_id: '', is_client_facing: false, description: '' };
            this.showTaskModal = true;
        },

        async saveTask() {
            if (!this.taskForm.task_name.trim()) { window.toast.warning('업무명을 입력해주세요.'); return; }
            this.taskSaving = true;
            try {
                const body = { ...this.taskForm, project_id: this.project.id };
                body.assignee_id = body.assignee_id ? parseInt(body.assignee_id) : null;
                await api.post('/tasks', body);
                window.toast.success('업무가 생성되었습니다.');
                this.showTaskModal = false;
                await this.load(this.project.id);
            } catch (e) { window.toast.error(e.message); }
            finally { this.taskSaving = false; }
        },

        // 업무 상태 변경
        async changeTaskStatus(task, newStatus) {
            try {
                await api.patch(`/tasks/${task.id}/status`, { status: newStatus });
                task.status = newStatus;
                window.toast.success('상태가 변경되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        // 업무 상세
        openTaskDetail(task) {
            this.selectedTask = { ...task };
            this.showTaskDetailModal = true;
        },

        // 프로젝트 상태 변경
        async changeProjectStatus(newStatus) {
            try {
                await api.patch(`/projects/${this.project.id}/status`, { status: newStatus });
                this.project.status = newStatus;
                window.toast.success('프로젝트 상태가 변경되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        // 프로젝트 편집
        async openEdit() {
            if (!this.project) return;
            this.form = {
                project_name: this.project.project_name, project_type: this.project.project_type,
                client_id: this.project.client_id || '', description: this.project.description || '',
                start_date: this.project.start_date || '', end_date: this.project.end_date || '',
                contract_amount: this.project.contract_amount || '',
                _client_name: this.project.client_name || '',
            };
            this.showEditModal = true;
        },

        async saveProject() {
            if (!this.form.project_name?.trim()) { window.toast.warning('프로젝트명을 입력해주세요.'); return; }
            if (this.form.project_type === 'outsourcing' && !this.form.client_id) { window.toast.warning('외주 프로젝트는 발주처를 선택해주세요.'); return; }
            this.saving = true;
            try {
                const body = { ...this.form };
                body.client_id = body.client_id ? parseInt(body.client_id) : null;
                this.project = await api.put(`/projects/${this.project.id}`, body);
                window.toast.success('프로젝트가 수정되었습니다.');
                this.showEditModal = false;
            } catch (e) { window.toast.error(e.message); }
            finally { this.saving = false; }
        },

        async deleteProject() {
            if (!await window.confirmDialog('이 프로젝트를 삭제하시겠습니까?', { title: '프로젝트 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/projects/${this.project.id}`);
                window.toast.success('프로젝트가 삭제되었습니다.');
                window.location.hash = '#/projects';
            } catch (e) { window.toast.error(e.message); }
        },

        // 업무 삭제
        async deleteTask(taskId) {
            if (!await window.confirmDialog('이 업무를 삭제하시겠습니까?', { title: '업무 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/tasks/${taskId}`);
                this.tasks = this.tasks.filter(t => t.id !== taskId);
                this.showTaskDetailModal = false;
                window.toast.success('업무가 삭제되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        // 포털 토큰 관리
        async openPortalModal() {
            this.showPortalModal = true;
            this.portalLoading = true;
            try {
                const res = await api.get(`/projects/${this.project.id}/portal-token`);
                this.portalToken = res?.token ? res : null;
            } catch { this.portalToken = null; }
            finally { this.portalLoading = false; }
        },

        async createPortalToken() {
            this.portalLoading = true;
            try {
                this.portalToken = await api.post(`/projects/${this.project.id}/portal-token`, {});
                window.toast.success('포털 링크가 생성되었습니다.');
            } catch (e) { window.toast.error(e.message); }
            finally { this.portalLoading = false; }
        },

        async revokePortalToken() {
            if (!this.portalToken) return;
            if (!await window.confirmDialog('포털 링크를 비활성화하시겠습니까?', { title: '포털 링크 비활성화', confirmText: '비활성화', danger: true })) return;
            try {
                await api.del(`/portal-tokens/${this.portalToken.id}`);
                this.portalToken = null;
                window.toast.success('포털 링크가 비활성화되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        copyPortalUrl() {
            if (!this.portalToken?.portal_url) return;
            const url = this.portalToken.portal_url.replace(/\/api\/v1\/portal\//, '/#/portal/').replace(/\/data$/, '');
            navigator.clipboard.writeText(url).then(
                () => window.toast.success('포털 URL이 복사되었습니다.'),
                () => window.toast.error('복사에 실패했습니다.')
            );
        },
    };
}

// ============================================================
// 업무 목록 페이지
// ============================================================

function taskListPage() {
    return {
        tasks: [], total: 0, loading: true,
        search: '', statusFilter: '', priorityFilter: '', projectFilter: '',
        page: 1, size: 20,
        viewMode: 'list',
        showCreateModal: false, saving: false,
        showDetailModal: false, selectedTask: null,
        form: { task_name: '', project_id: '', phase: '', priority: '보통', due_date: '', start_date: '', assignee_id: '', is_client_facing: false, description: '' },

        kanbanColumns: [
            { status: 'pending', label: '대기', dotColor: 'bg-gray-400' },
            { status: 'in_progress', label: '진행중', dotColor: 'bg-blue-500' },
            { status: 'feedback_pending', label: '피드백 대기', dotColor: 'bg-orange-500' },
            { status: 'completed', label: '완료', dotColor: 'bg-green-500' },
        ],

        async init() {
            await this.loadTasks();
        },

        async loadTasks() {
            this.loading = true;
            try {
                let url = `/tasks?page=${this.page}&size=${this.size}`;
                if (this.search) url += `&search=${encodeURIComponent(this.search)}`;
                if (this.statusFilter) url += `&status=${this.statusFilter}`;
                if (this.priorityFilter) url += `&priority=${encodeURIComponent(this.priorityFilter)}`;
                if (this.projectFilter) url += `&project_id=${this.projectFilter}`;
                const data = await api.get(url);
                this.tasks = data?.tasks || [];
                this.total = data?.total || 0;
            } catch (e) { window.toast.error('업무 목록 로드 실패'); }
            finally { this.loading = false; }
        },

        openCreate() {
            this.form = { task_name: '', project_id: '', phase: '', priority: '보통', due_date: '', start_date: '', assignee_id: '', is_client_facing: false, description: '' };
            this.showCreateModal = true;
        },

        async save() {
            if (!this.form.task_name.trim()) { window.toast.warning('업무명을 입력해주세요.'); return; }
            this.saving = true;
            try {
                const body = { ...this.form };
                body.project_id = body.project_id ? parseInt(body.project_id) : null;
                body.assignee_id = body.assignee_id ? parseInt(body.assignee_id) : null;
                await api.post('/tasks', body);
                window.toast.success('업무가 생성되었습니다.');
                this.showCreateModal = false;
                await this.loadTasks();
            } catch (e) { window.toast.error(e.message); }
            finally { this.saving = false; }
        },

        openDetail(task) { this.selectedTask = { ...task }; this.showDetailModal = true; },

        async changeStatus(task, newStatus) {
            try {
                await api.patch(`/tasks/${task.id}/status`, { status: newStatus });
                task.status = newStatus;
                if (this.selectedTask?.id === task.id) this.selectedTask.status = newStatus;
                window.toast.success('상태가 변경되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        async deleteTask(taskId) {
            if (!await window.confirmDialog('이 업무를 삭제하시겠습니까?', { title: '업무 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/tasks/${taskId}`);
                this.tasks = this.tasks.filter(t => t.id !== taskId);
                this.showDetailModal = false;
                window.toast.success('업무가 삭제되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        getKanbanTasks(status) {
            return this.tasks.filter(t => t.status === status).sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
        },

        // ---- 칸반 드래그앤드롭 ----
        dragTaskId: null,
        dragOverCol: null,
        dragOverTaskId: null,
        dragInsertBefore: false,

        onDragStart(e, task) {
            this.dragTaskId = task.id;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', task.id);
            e.target.classList.add('opacity-50');
        },

        onDragEnd(e) {
            e.target.classList.remove('opacity-50');
            this.dragTaskId = null;
            this.dragOverCol = null;
            this.dragOverTaskId = null;
        },

        onDragOverCol(e, colStatus) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            this.dragOverCol = colStatus;
        },

        onDragOverCard(e, task) {
            e.preventDefault();
            e.stopPropagation();
            const rect = e.currentTarget.getBoundingClientRect();
            this.dragInsertBefore = (e.clientY - rect.top) < rect.height / 2;
            this.dragOverTaskId = task.id;
        },

        onDragLeaveCard() {
            this.dragOverTaskId = null;
        },

        async onDropCol(e, colStatus) {
            e.preventDefault();
            const taskId = this.dragTaskId;
            if (!taskId) return;
            const task = this.tasks.find(t => t.id === taskId);
            if (!task) return;

            const oldStatus = task.status;
            const colTasks = this.getKanbanTasks(colStatus).filter(t => t.id !== taskId);

            // 드롭 위치 계산
            let insertIndex = colTasks.length;
            if (this.dragOverTaskId) {
                const overIdx = colTasks.findIndex(t => t.id === this.dragOverTaskId);
                if (overIdx >= 0) {
                    insertIndex = this.dragInsertBefore ? overIdx : overIdx + 1;
                }
            }

            // 상태 변경
            if (oldStatus !== colStatus) {
                try {
                    await api.patch(`/tasks/${taskId}/status`, { status: colStatus });
                    task.status = colStatus;
                } catch (err) {
                    window.toast.error(err.message || '상태 변경 실패');
                    this.dragOverCol = null;
                    this.dragOverTaskId = null;
                    return;
                }
            }

            // 순서 변경
            colTasks.splice(insertIndex, 0, task);
            const orders = colTasks.map((t, i) => ({ task_id: t.id, sort_order: i }));
            orders.forEach(o => { const t = this.tasks.find(x => x.id === o.task_id); if (t) t.sort_order = o.sort_order; });

            try {
                await api.patch('/tasks/reorder', { task_orders: orders });
            } catch {}

            if (oldStatus !== colStatus) window.toast.success('상태가 변경되었습니다.');

            this.dragOverCol = null;
            this.dragOverTaskId = null;
        },

        doSearch: debounce(function() { this.page = 1; this.loadTasks(); }, 300),

        get totalPages() { return Math.ceil(this.total / this.size) || 1; },
        goPage(p) { if (p >= 1 && p <= this.totalPages) { this.page = p; this.loadTasks(); } },
    };
}

// ============================================================
// 문서 업로드 페이지
// ============================================================

function documentUploadPage() {
    return {
        selectedFile: null, dragOver: false, validationError: '',
        selectedProject: '', selectedType: 'contract', docTitle: '', docDescription: '',
        autoAnalyze: true, uploadState: 'idle', uploadProgress: 0,
        saving: false,

        docTypes: [
            { code: 'estimate', label: '견적서', desc: 'Sheets 연동' },
            { code: 'contract', label: '계약서', desc: 'AI 분석' },
            { code: 'proposal', label: '제안서', desc: '조건 추출' },
            { code: 'other', label: '기타', desc: '일반 첨부' },
        ],

        allowedExtensions: ['pdf','docx','doc','hwp','hwpx','jpg','jpeg','png','tiff','tif','bmp','webp'],
        maxFileSize: 50 * 1024 * 1024,

        async init() {
            const m = (window.location.hash || '').match(/^#\/projects\/(\d+)\/documents\/upload$/);
            if (m) this.selectedProject = m[1];
        },

        handleDrop(e) { this.dragOver = false; if (e.dataTransfer.files.length) this.validateFile(e.dataTransfer.files[0]); },
        handleFileSelect(e) { if (e.target.files.length) this.validateFile(e.target.files[0]); },

        validateFile(file) {
            this.validationError = '';
            const ext = file.name.split('.').pop().toLowerCase();
            if (!this.allowedExtensions.includes(ext)) { this.validationError = '지원하지 않는 파일 형식입니다.'; this.selectedFile = null; return; }
            if (file.size > this.maxFileSize) { this.validationError = '파일 크기는 50MB를 초과할 수 없습니다.'; this.selectedFile = null; return; }
            this.selectedFile = file;
            if (!this.docTitle) this.docTitle = file.name.replace(/\.[^/.]+$/, '');
        },

        removeFile() { this.selectedFile = null; this.validationError = ''; },

        formatFileSize(bytes) {
            if (!bytes) return '0 B';
            const k = 1024, sizes = ['B','KB','MB','GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        },

        getFileExt(name) { return name.split('.').pop().toUpperCase(); },
        getFileIconBg(name) {
            const ext = name.split('.').pop().toLowerCase();
            return { pdf:'bg-red-500', docx:'bg-blue-600', doc:'bg-blue-600', hwp:'bg-cyan-600', hwpx:'bg-cyan-600' }[ext] || 'bg-green-500';
        },

        get canUpload() { return this.selectedFile && this.docTitle && this.selectedProject && !this.validationError && this.uploadState === 'idle'; },

        async startUpload() {
            if (!this.canUpload) return;
            this.saving = true;
            this.uploadState = 'uploading'; this.uploadProgress = 30;
            try {
                const formData = new FormData();
                formData.append('file', this.selectedFile);
                formData.append('document_type', this.selectedType);
                formData.append('title', this.docTitle);
                this.uploadProgress = 60;
                const res = await fetch(`/api/v1/projects/${this.selectedProject}/documents`, { method: 'POST', body: formData, credentials: 'include' });
                this.uploadProgress = 90;
                if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || '업로드 실패'); }
                const doc = await res.json();
                this.uploadProgress = 100;
                this.uploadState = 'done';
                window.toast.success('문서가 업로드되었습니다.');
                setTimeout(() => {
                    if (doc.document_type === 'estimate' && doc.google_sheet_id) {
                        window.location.hash = `#/documents/${doc.id}/estimate`;
                    } else {
                        window.location.hash = `#/documents/${doc.id}`;
                    }
                }, 800);
            } catch (e) { window.toast.error(e.message); this.uploadState = 'idle'; this.uploadProgress = 0; }
            finally { this.saving = false; }
        },
    };
}

// ============================================================
// 문서 상세 페이지
// ============================================================

function documentDetailPage() {
    return {
        doc: null, loading: true,
        activeTab: 'analysis',
        reviews: [], versions: [],
        extractedTasks: [], selectedTaskIds: [],
        showGenerateModal: false, generating: false,

        tabs: [
            { id: 'analysis', label: 'AI 분석' },
            { id: 'preview', label: '문서 보기' },
            { id: 'review', label: '검토' },
            { id: 'versions', label: '버전 이력' },
        ],

        async init() {
            const m = (window.location.hash || '').match(/^#\/documents\/(\d+)$/);
            if (m) await this.load(parseInt(m[1]));
        },

        async load(id) {
            this.loading = true;
            try {
                const [doc, reviewData, verData] = await Promise.all([
                    api.get(`/documents/${id}`),
                    api.get(`/documents/${id}/reviews`).catch(() => []),
                    api.get(`/documents/${id}/versions`).catch(() => ({ versions: [] })),
                ]);
                this.doc = doc;
                this.reviews = Array.isArray(reviewData) ? reviewData : [];
                this.versions = verData?.versions || [];

                // AI 분석 결과에서 추출된 업무
                if (doc.ai_analysis) {
                    try {
                        const analysis = typeof doc.ai_analysis === 'string' ? JSON.parse(doc.ai_analysis) : doc.ai_analysis;
                        this.extractedTasks = analysis?.tasks || analysis?.extracted_tasks || [];
                    } catch { this.extractedTasks = []; }
                }
            } catch (e) { window.toast.error('문서를 불러올 수 없습니다.'); }
            finally { this.loading = false; }
        },

        toggleTaskSelection(idx) {
            const i = this.selectedTaskIds.indexOf(idx);
            if (i >= 0) this.selectedTaskIds.splice(i, 1);
            else this.selectedTaskIds.push(idx);
        },

        toggleAllTasks() {
            if (this.selectedTaskIds.length === this.extractedTasks.length) this.selectedTaskIds = [];
            else this.selectedTaskIds = this.extractedTasks.map((_, i) => i);
        },

        async generateTasks() {
            if (!this.selectedTaskIds.length) return;
            this.generating = true;
            try {
                const res = await api.post(`/documents/${this.doc.id}/generate-tasks`, { selected_task_indices: this.selectedTaskIds });
                window.toast.success(res.message || '업무가 생성되었습니다.');
                this.selectedTaskIds = [];
            } catch (e) { window.toast.error(e.message); }
            finally { this.generating = false; }
        },

        async requestAiAnalysis() {
            try {
                await api.post(`/documents/${this.doc.id}/ai-highlights`);
                window.toast.success('AI 분석이 완료되었습니다.');
                await this.load(this.doc.id);
            } catch (e) { window.toast.error(e.message); }
        },

        async downloadDoc() {
            window.open(`/api/v1/documents/${this.doc.id}/download`, '_blank');
        },

        async deleteDoc() {
            if (!await window.confirmDialog('이 문서를 삭제하시겠습니까?', { title: '문서 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/documents/${this.doc.id}`);
                window.toast.success('문서가 삭제되었습니다.');
                window.location.hash = `#/projects/${this.doc.project_id}`;
            } catch (e) { window.toast.error(e.message); }
        },

        getTypeBadge(type) { return { estimate:'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400', contract:'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400', proposal:'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400' }[type] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'; },
        getTypeLabel(type) { return { estimate:'견적서', contract:'계약서', proposal:'제안서', other:'기타' }[type] || type; },

        getStatusBadge(status) { return { uploaded:'bg-gray-100 text-gray-600', analyzing:'bg-yellow-100 text-yellow-700', review_pending:'bg-blue-100 text-blue-700', revision_requested:'bg-red-100 text-red-700', confirmed:'bg-green-100 text-green-700' }[status] || 'bg-gray-100 text-gray-600'; },
        getStatusLabel(status) { return { uploaded:'업로드됨', analyzing:'분석중', review_pending:'검토 대기', revision_requested:'수정 요청', confirmed:'확정' }[status] || status; },
    };
}

// ============================================================
// 견적서 Sheets 페이지
// ============================================================

function estimateSheetsPage() {
    return {
        doc: null, loading: true,
        activeTab: 'sheet',
        sheetData: null, parsedData: null,
        isSyncing: false, isParsing: false,
        showConnectModal: false, connectMethod: '', sheetUrl: '',

        async init() {
            const m = (window.location.hash || '').match(/^#\/documents\/(\d+)\/estimate$/);
            if (m) await this.load(parseInt(m[1]));
        },

        async load(id) {
            this.loading = true;
            try {
                this.doc = await api.get(`/documents/${id}`);
                if (this.doc.google_sheet_id) {
                    try { this.sheetData = await api.get(`/documents/${id}/sheet-data`); } catch {}
                }
            } catch (e) { window.toast.error('견적서를 불러올 수 없습니다.'); }
            finally { this.loading = false; }
        },

        async syncSheet() {
            if (!this.doc?.id || this.isSyncing) return;
            this.isSyncing = true;
            try {
                this.sheetData = await api.get(`/documents/${this.doc.id}/sheet-data`);
                window.toast.success('동기화 완료');
            } catch (e) { window.toast.error(e.message); }
            finally { this.isSyncing = false; }
        },

        async parseWithAi() {
            if (!this.doc?.id || this.isParsing) return;
            this.isParsing = true;
            try {
                const res = await api.post(`/documents/${this.doc.id}/sheet-parse`);
                this.parsedData = res?.data || null;
                window.toast.success('AI 파싱 완료');
                this.activeTab = 'parsed';
            } catch (e) { window.toast.error(e.message); }
            finally { this.isParsing = false; }
        },

        async connectSheet() {
            if (!this.doc?.project_id) return;
            try {
                if (this.connectMethod === 'new') {
                    const formData = new FormData();
                    formData.append('title', this.doc.title || '견적서');
                    const res = await fetch(`/api/v1/projects/${this.doc.project_id}/sheets/create`, { method: 'POST', body: formData, credentials: 'include' });
                    if (!res.ok) throw new Error('시트 생성 실패');
                    const newDoc = await res.json();
                    window.toast.success('Google Sheet가 생성되었습니다.');
                    this.showConnectModal = false;
                    window.location.hash = `#/documents/${newDoc.id}/estimate`;
                } else if (this.connectMethod === 'link' && this.sheetUrl) {
                    const formData = new FormData();
                    formData.append('sheet_url', this.sheetUrl);
                    formData.append('title', this.doc.title || '견적서');
                    const res = await fetch(`/api/v1/projects/${this.doc.project_id}/sheets/link`, { method: 'POST', body: formData, credentials: 'include' });
                    if (!res.ok) throw new Error('시트 연결 실패');
                    const newDoc = await res.json();
                    window.toast.success('Google Sheet가 연결되었습니다.');
                    this.showConnectModal = false;
                    window.location.hash = `#/documents/${newDoc.id}/estimate`;
                }
            } catch (e) { window.toast.error(e.message); }
        },

        formatNumber(n) { return n ? Number(n).toLocaleString() : '0'; },

        getSheetUrl() {
            if (!this.doc?.google_sheet_id) return '#';
            return `https://docs.google.com/spreadsheets/d/${this.doc.google_sheet_id}/edit`;
        },
    };
}

// ============================================================
// 완료 보고 작성 페이지
// ============================================================

function completionReportPage() {
    return {
        task: null, loading: true,
        report: null, reportHistory: [],
        showReportModal: false, showPreviewModal: false,
        sending: false, aiDrafting: false,

        form: {
            recipient_email: '', cc_emails: [], subject: '', body_html: '',
            scheduled_at: null,
        },
        ccInput: '',
        sendOption: 'now',
        scheduleDate: '', scheduleTime: '',

        async init() {
            const m = (window.location.hash || '').match(/^#\/tasks\/(\d+)\/completion-report$/);
            if (m) await this.load(parseInt(m[1]));
        },

        async load(taskId) {
            this.loading = true;
            try {
                this.task = await api.get(`/tasks/${taskId}`);
                // 기존 보고서 로드
                try { this.report = await api.get(`/tasks/${taskId}/completion-report`); } catch { this.report = null; }
                // 기본 제목 설정
                if (!this.form.subject && this.task) {
                    this.form.subject = `[완료 보고] ${this.task.task_name}`;
                }
            } catch (e) { window.toast.error('업무를 불러올 수 없습니다.'); }
            finally { this.loading = false; }
        },

        openReportModal() {
            if (this.task) {
                if (!this.form.subject) this.form.subject = `[완료 보고] ${this.task.task_name}`;
            }
            this.showReportModal = true;
        },

        addCcEmail() {
            const email = this.ccInput.trim();
            if (email && email.includes('@') && !this.form.cc_emails.includes(email)) {
                this.form.cc_emails.push(email);
            }
            this.ccInput = '';
        },

        removeCcEmail(idx) { this.form.cc_emails.splice(idx, 1); },

        async generateAiDraft() {
            if (!this.task?.id || this.aiDrafting) return;
            this.aiDrafting = true;
            try {
                const res = await api.post(`/tasks/${this.task.id}/ai-draft-report`);
                if (res.subject) this.form.subject = res.subject;
                if (res.body_html) this.form.body_html = res.body_html;
                window.toast.success('AI 초안이 생성되었습니다.');
            } catch (e) { window.toast.error(e.message || 'AI 초안 생성 실패'); }
            finally { this.aiDrafting = false; }
        },

        async sendReport() {
            if (!this.form.recipient_email || !this.form.subject || !this.form.body_html) {
                window.toast.warning('수신자, 제목, 본문을 모두 입력해주세요.');
                return;
            }
            this.sending = true;
            try {
                const body = { ...this.form };
                if (this.sendOption === 'schedule' && this.scheduleDate && this.scheduleTime) {
                    body.scheduled_at = `${this.scheduleDate}T${this.scheduleTime}:00`;
                } else {
                    body.scheduled_at = null;
                }
                const res = await api.post(`/tasks/${this.task.id}/completion-report`, body);
                this.report = res;
                this.showReportModal = false;
                window.toast.success(this.sendOption === 'schedule' ? '보고가 예약되었습니다.' : '보고가 발송되었습니다.');
            } catch (e) { window.toast.error(e.message); }
            finally { this.sending = false; }
        },

        async resendReport() {
            if (!this.report?.id) return;
            try {
                await api.post(`/completion-reports/${this.report.id}/resend`);
                window.toast.success('보고가 재발송되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        async deleteReport() {
            if (!this.report?.id) return;
            if (!await window.confirmDialog('이 보고를 삭제하시겠습니까?', { title: '보고 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/completion-reports/${this.report.id}`);
                this.report = null;
                window.toast.success('보고가 삭제되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        openPreview() { this.showPreviewModal = true; },

        getReportStatusBadge(status) {
            return { draft:'bg-gray-100 text-gray-600', scheduled:'bg-yellow-100 text-yellow-700', sent:'bg-green-100 text-green-700', failed:'bg-red-100 text-red-700' }[status] || 'bg-gray-100 text-gray-600';
        },
        getReportStatusLabel(status) {
            return { draft:'초안', scheduled:'예약됨', sent:'발송됨', failed:'실패' }[status] || status;
        },
    };
}

// ============================================================
// [Phase 2] 피드백 페이지 (비로그인, 토큰 기반)
// ============================================================

function feedbackPage() {
    return {
        loading: true,
        token: '',
        report: null,
        existingFeedbacks: [],
        feedbackState: 'default',
        revisionContent: '',
        commentContent: '',
        commentName: '',
        submitting: false,
        error: null,
        daysRemaining: 0,
        tokenExpiry: '',
        isTokenExpired: false,

        init() {
            const hash = window.location.hash || '';
            const m = hash.match(/^#\/feedback\/([a-zA-Z0-9_-]+)/);
            if (m) {
                this.token = m[1];
                this.load();
            } else {
                this.error = '유효하지 않은 피드백 링크입니다.';
                this.loading = false;
            }
        },

        async load() {
            try {
                const data = await api.get(`/feedback/${this.token}`);
                this.report = data;
                this.existingFeedbacks = data.existing_feedbacks || [];
                if (data.sent_at) {
                    const sent = new Date(data.sent_at);
                    const expiry = new Date(sent.getTime() + 30 * 24 * 60 * 60 * 1000);
                    const now = new Date();
                    this.isTokenExpired = now > expiry;
                    this.daysRemaining = Math.max(0, Math.ceil((expiry - now) / (1000 * 60 * 60 * 24)));
                    this.tokenExpiry = expiry.toLocaleDateString('ko-KR');
                }
                const last = this.existingFeedbacks[0];
                if (last) {
                    if (last.feedback_type === 'confirmed') this.feedbackState = 'confirm_success';
                    else if (last.feedback_type === 'revision') this.feedbackState = 'revision_success';
                }
            } catch (e) {
                this.error = e.message;
            } finally { this.loading = false; }
        },

        async confirmComplete() {
            this.submitting = true;
            try {
                await api.post(`/feedback/${this.token}`, { feedback_type: 'confirmed' });
                this.feedbackState = 'confirm_success';
            } catch (e) { window.toast.error(e.message); }
            finally { this.submitting = false; }
        },

        showRevisionForm() {
            this.feedbackState = 'revision_form';
            this.revisionContent = '';
        },

        async submitRevision() {
            if (!this.revisionContent.trim()) return;
            this.submitting = true;
            try {
                await api.post(`/feedback/${this.token}`, {
                    feedback_type: 'revision',
                    content: this.revisionContent.trim(),
                });
                this.feedbackState = 'revision_success';
            } catch (e) { window.toast.error(e.message); }
            finally { this.submitting = false; }
        },

        showCommentForm() {
            this.feedbackState = 'comment_form';
            this.commentContent = '';
            this.commentName = '';
        },

        async submitComment() {
            if (!this.commentContent.trim()) return;
            this.submitting = true;
            try {
                await api.post(`/feedback/${this.token}`, {
                    feedback_type: 'comment',
                    content: this.commentContent.trim(),
                    client_name: this.commentName.trim() || null,
                });
                this.feedbackState = 'comment_success';
            } catch (e) { window.toast.error(e.message); }
            finally { this.submitting = false; }
        },

        getFeedbackTypeLabel(t) {
            return { confirmed: '확인 완료', revision: '수정 요청', comment: '의견' }[t] || t;
        },
        getFeedbackTypeBadge(t) {
            return { confirmed: 'bg-green-100 text-green-700', revision: 'bg-red-100 text-red-700', comment: 'bg-blue-100 text-blue-700' }[t] || 'bg-gray-100 text-gray-600';
        },
    };
}

// ============================================================
// [Phase 3] 보고서 허브 페이지
// ============================================================

function reportHubPage() {
    return {
        loading: true,
        reports: [],
        total: 0,
        page: 1,
        size: 20,
        showGenerateModal: false,
        generating: false,
        genForm: { project_id: '', report_type: 'periodic', period_start: '', period_end: '' },

        init() { this.load(); },

        async load() {
            this.loading = true;
            try {
                const data = await api.get(`/reports?page=${this.page}&size=${this.size}`);
                this.reports = data.reports || [];
                this.total = data.total || 0;
            } catch (e) { window.toast.error(e.message); }
            finally { this.loading = false; }
        },

        get totalPages() { return Math.max(1, Math.ceil(this.total / this.size)); },
        goPage(p) { if (p >= 1 && p <= this.totalPages) { this.page = p; this.load(); } },

        openGenerate() {
            const today = new Date();
            const weekAgo = new Date(today); weekAgo.setDate(today.getDate() - 7);
            this.genForm = {
                project_id: '',
                report_type: 'periodic',
                period_start: weekAgo.toISOString().split('T')[0],
                period_end: today.toISOString().split('T')[0],
            };
            this.showGenerateModal = true;
        },

        async generate() {
            if (!this.genForm.project_id) { window.toast.warning('프로젝트를 선택하세요.'); return; }
            this.generating = true;
            try {
                const body = { report_type: this.genForm.report_type };
                if (this.genForm.report_type === 'periodic') {
                    body.period_start = this.genForm.period_start;
                    body.period_end = this.genForm.period_end;
                }
                const report = await api.post(`/projects/${this.genForm.project_id}/reports/generate`, body);
                this.showGenerateModal = false;
                window.toast.success('보고서가 생성되었습니다.');
                window.location.hash = `#/reports/${report.id}`;
            } catch (e) { window.toast.error(e.message); }
            finally { this.generating = false; }
        },

        async deleteReport(id) {
            if (!await window.confirmDialog('이 보고서를 삭제하시겠습니까?', { title: '보고서 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/reports/${id}`);
                window.toast.success('삭제되었습니다.');
                this.load();
            } catch (e) { window.toast.error(e.message); }
        },

        getTypeBadge(t) { return t === 'periodic' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' : 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300'; },
        getTypeLabel(t) { return t === 'periodic' ? '정기 보고' : '완료 보고'; },
        getStatusBadge(s) { return s === 'sent' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'; },
        getStatusLabel(s) { return s === 'sent' ? '발송됨' : '초안'; },
    };
}

// ============================================================
// [Phase 3] 보고서 편집기 페이지
// ============================================================

function reportEditorPage() {
    return {
        loading: true,
        report: null,
        editing: false,
        saving: false,
        editForm: { title: '', content_html: '' },
        showSendModal: false,
        sending: false,
        sendEmails: '',
        error: null,

        init() {
            const hash = window.location.hash || '';
            const m = hash.match(/^#\/reports\/(\d+)/);
            if (m) this.load(parseInt(m[1]));
            else { this.error = '잘못된 접근입니다.'; this.loading = false; }
        },

        async load(id) {
            try {
                this.report = await api.get(`/reports/${id}`);
            } catch (e) { this.error = e.message; }
            finally { this.loading = false; }
        },

        startEdit() {
            this.editForm.title = this.report.title;
            this.editForm.content_html = this.report.content_html;
            this.editing = true;
        },

        cancelEdit() { this.editing = false; },

        async saveEdit() {
            this.saving = true;
            try {
                const body = {};
                if (this.editForm.title !== this.report.title) body.title = this.editForm.title;
                if (this.editForm.content_html !== this.report.content_html) body.content_html = this.editForm.content_html;
                if (Object.keys(body).length === 0) { this.editing = false; return; }
                this.report = await api.put(`/reports/${this.report.id}`, body);
                this.editing = false;
                window.toast.success('저장되었습니다.');
            } catch (e) { window.toast.error(e.message); }
            finally { this.saving = false; }
        },

        openSend() { this.sendEmails = ''; this.showSendModal = true; },

        async send() {
            const emails = this.sendEmails.split(/[,;\n]+/).map(e => e.trim()).filter(Boolean);
            if (emails.length === 0) { window.toast.warning('수신자 이메일을 입력하세요.'); return; }
            this.sending = true;
            try {
                this.report = await api.post(`/reports/${this.report.id}/send`, { recipient_emails: emails });
                this.showSendModal = false;
                window.toast.success('보고서가 발송되었습니다.');
            } catch (e) { window.toast.error(e.message); }
            finally { this.sending = false; }
        },

        async deleteReport() {
            if (!await window.confirmDialog('이 보고서를 삭제하시겠습니까?', { title: '보고서 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/reports/${this.report.id}`);
                window.toast.success('삭제되었습니다.');
                window.location.hash = '#/reports';
            } catch (e) { window.toast.error(e.message); }
        },

        getTypeBadge(t) { return t === 'periodic' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' : 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300'; },
        getTypeLabel(t) { return t === 'periodic' ? '정기 보고' : '완료 보고'; },
        getStatusBadge(s) { return s === 'sent' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'; },
        getStatusLabel(s) { return s === 'sent' ? '발송됨' : '초안'; },
    };
}

/* ───────── 수금 관리 페이지 ───────── */
function paymentPage() {
    return {
        loading: true, payments: [], total: 0,
        summary: { total_amount: 0, paid_amount: 0, pending_amount: 0, overdue_amount: 0, upcoming_payments: [] },
        statusFilter: '', page: 1, size: 20,
        showCreateModal: false, creating: false,
        createForm: { project_id: '', payment_type: 'advance', description: '', amount: '', due_date: '', memo: '' },
        showUpdateModal: false, updating: false, updateTarget: null,
        updateForm: { status: '', paid_date: '', paid_amount: '', memo: '' },

        async init() { await Promise.all([this.loadSummary(), this.loadPayments()]); this.loading = false; },

        async loadSummary() {
            try { this.summary = await api.get('/payments/summary'); } catch (e) { console.error(e); }
        },

        async loadPayments() {
            try {
                const params = new URLSearchParams({ page: this.page, size: this.size });
                if (this.statusFilter) params.set('status', this.statusFilter);
                const res = await api.get(`/payments?${params}`);
                this.payments = res.payments; this.total = res.total;
            } catch (e) { window.toast.error(e.message); }
        },

        filterStatus(s) { this.statusFilter = s; this.page = 1; this.loadPayments(); },

        get totalPages() { return Math.max(1, Math.ceil(this.total / this.size)); },
        goPage(p) { if (p >= 1 && p <= this.totalPages) { this.page = p; this.loadPayments(); } },

        openCreate() {
            this.createForm = { project_id: '', payment_type: 'advance', description: '', amount: '', due_date: '', memo: '' };
            this.showCreateModal = true;
        },

        async create() {
            if (!this.createForm.project_id || !this.createForm.amount || !this.createForm.due_date) { window.toast.warning('필수 항목을 입력하세요.'); return; }
            this.creating = true;
            try {
                await api.post(`/projects/${this.createForm.project_id}/payments`, {
                    payment_type: this.createForm.payment_type, description: this.createForm.description || null,
                    amount: parseInt(this.createForm.amount), due_date: this.createForm.due_date, memo: this.createForm.memo || null,
                });
                this.showCreateModal = false;
                window.toast.success('결제 일정이 등록되었습니다.');
                await Promise.all([this.loadSummary(), this.loadPayments()]);
            } catch (e) { window.toast.error(e.message); }
            finally { this.creating = false; }
        },

        openUpdate(p) {
            this.updateTarget = p;
            this.updateForm = { status: p.status, paid_date: p.paid_date || '', paid_amount: p.paid_amount || '', memo: p.memo || '' };
            this.showUpdateModal = true;
        },

        async update() {
            this.updating = true;
            try {
                const body = { status: this.updateForm.status };
                if (this.updateForm.paid_date) body.paid_date = this.updateForm.paid_date;
                if (this.updateForm.paid_amount) body.paid_amount = parseInt(this.updateForm.paid_amount);
                if (this.updateForm.memo) body.memo = this.updateForm.memo;
                await api.patch(`/payments/${this.updateTarget.id}`, body);
                this.showUpdateModal = false;
                window.toast.success('결제 상태가 수정되었습니다.');
                await Promise.all([this.loadSummary(), this.loadPayments()]);
            } catch (e) { window.toast.error(e.message); }
            finally { this.updating = false; }
        },

        fmtAmount(n) { return (n || 0).toLocaleString('ko-KR'); },
        getTypeBadge(t) {
            const m = { advance: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300', interim: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300', final: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300', milestone: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300' };
            return m[t] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
        },
        getTypeLabel(t) {
            const m = { advance: '선급금', interim: '중도금', final: '잔금', milestone: '마일스톤' };
            return m[t] || t;
        },
        getStatusBadge(s) {
            const m = { pending: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300', invoiced: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300', paid: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300', overdue: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' };
            return m[s] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
        },
        getStatusLabel(s) {
            const m = { pending: '대기', invoiced: '청구', paid: '수금완료', overdue: '연체' };
            return m[s] || s;
        },
    };
}

/* ───────── AI 견적서 페이지 ───────── */
function estimatePage() {
    return {
        loading: false, generating: false, exporting: false,
        projectType: 'outsourcing', scopeDescription: '',
        result: null, selectedProjectId: '', exportTitle: 'AI 견적서',
        showExportModal: false,

        async generate() {
            if (!this.scopeDescription || this.scopeDescription.length < 10) { window.toast.warning('프로젝트 범위를 10자 이상 입력하세요.'); return; }
            this.generating = true; this.result = null;
            try {
                this.result = await api.post('/ai/estimate/generate', { project_type: this.projectType, scope_description: this.scopeDescription });
                window.toast.success('AI 견적이 생성되었습니다.');
            } catch (e) { window.toast.error(e.message); }
            finally { this.generating = false; }
        },

        openExport() {
            if (!this.result) return;
            this.exportTitle = 'AI 견적서';
            this.selectedProjectId = '';
            this.showExportModal = true;
        },

        async exportSheet() {
            if (!this.selectedProjectId) { window.toast.warning('프로젝트를 선택하세요.'); return; }
            this.exporting = true;
            try {
                const res = await api.post('/ai/estimate/export-sheet', {
                    project_id: parseInt(this.selectedProjectId), title: this.exportTitle,
                    estimate_data: this.result,
                });
                this.showExportModal = false;
                window.toast.success('Google Sheet로 내보내기가 완료되었습니다.');
                window.open(res.sheet_url, '_blank');
            } catch (e) { window.toast.error(e.message); }
            finally { this.exporting = false; }
        },

        fmtAmount(n) { return (n || 0).toLocaleString('ko-KR'); },
    };
}

/* ───────── 템플릿 + 반복업무 페이지 ───────── */
function templatePage() {
    return {
        loading: true, tab: 'templates',
        /* ── 템플릿 ── */
        templates: [], totalTemplates: 0,
        showTplModal: false, savingTpl: false, editingTplId: null,
        tplForm: { name: '', project_type: 'outsourcing', description: '', team_id: '', task_templates: [], schedule_templates: [] },
        showTplDetail: false, detailTpl: null,
        get availableTeams() { return window._teams || []; },
        /* ── 반복업무 ── */
        recurringProject: '', recurringTasks: [],
        showRecModal: false, savingRec: false, editingRecId: null,
        recForm: { task_name: '', description: '', frequency: 'weekly', day_of_month: 1, day_of_week: 0, priority: '보통', assignee_id: '' },

        async init() {
            await this.loadTemplates();
            this.loading = false;
        },

        /* ── 템플릿 CRUD ── */
        async loadTemplates() {
            try {
                const res = await api.get('/templates');
                this.templates = res.templates; this.totalTemplates = res.total;
            } catch (e) { window.toast.error(e.message); }
        },

        openCreateTpl() {
            this.editingTplId = null;
            this.tplForm = { name: '', project_type: 'outsourcing', description: '', team_id: window._selectedTeamId || '', task_templates: [], schedule_templates: [] };
            this.showTplModal = true;
        },

        openEditTpl(t) {
            this.editingTplId = t.id;
            this.tplForm = {
                name: t.name, project_type: t.project_type, description: t.description || '',
                task_templates: JSON.parse(JSON.stringify(t.task_templates || [])),
                schedule_templates: JSON.parse(JSON.stringify(t.schedule_templates || [])),
            };
            this.showTplModal = true;
        },

        addTaskItem() {
            this.tplForm.task_templates.push({ task_name: '', phase: '', relative_due_days: 0, priority: '보통', is_client_facing: false });
        },
        removeTaskItem(idx) { this.tplForm.task_templates.splice(idx, 1); },

        addScheduleItem() {
            this.tplForm.schedule_templates.push({ phase: '', relative_start_days: 0, duration_days: 1 });
        },
        removeScheduleItem(idx) { this.tplForm.schedule_templates.splice(idx, 1); },

        async saveTpl() {
            if (!this.tplForm.name) { window.toast.warning('템플릿명을 입력하세요.'); return; }
            this.savingTpl = true;
            try {
                const body = { name: this.tplForm.name, project_type: this.tplForm.project_type, description: this.tplForm.description || null, task_templates: this.tplForm.task_templates.length ? this.tplForm.task_templates : null, schedule_templates: this.tplForm.schedule_templates.length ? this.tplForm.schedule_templates : null };
                if (this.editingTplId) {
                    const { project_type, ...updateBody } = body;
                    await api.put(`/templates/${this.editingTplId}`, updateBody);
                } else {
                    const teamId = this.tplForm.team_id;
                    const url = teamId ? `/templates?team_id=${teamId}` : '/templates';
                    await api.post(url, body);
                }
                this.showTplModal = false;
                window.toast.success(this.editingTplId ? '템플릿이 수정되었습니다.' : '템플릿이 저장되었습니다.');
                await this.loadTemplates();
            } catch (e) { window.toast.error(e.message); }
            finally { this.savingTpl = false; }
        },

        async deleteTpl(t) {
            if (!await window.confirmDialog(`"${t.name}" 템플릿을 삭제하시겠습니까?`, { title: '템플릿 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/templates/${t.id}`);
                window.toast.success('삭제되었습니다.');
                await this.loadTemplates();
            } catch (e) { window.toast.error(e.message); }
        },

        viewDetail(t) { this.detailTpl = t; this.showTplDetail = true; },

        /* ── 반복업무 ── */
        async loadRecurring() {
            if (!this.recurringProject) { this.recurringTasks = []; return; }
            try {
                this.recurringTasks = await api.get(`/projects/${this.recurringProject}/recurring-tasks`);
            } catch (e) { window.toast.error(e.message); }
        },

        openCreateRec() {
            if (!this.recurringProject) { window.toast.warning('프로젝트를 먼저 선택하세요.'); return; }
            this.editingRecId = null;
            this.recForm = { task_name: '', description: '', frequency: 'weekly', day_of_month: 1, day_of_week: 0, priority: '보통', assignee_id: '' };
            this.showRecModal = true;
        },

        openEditRec(r) {
            this.editingRecId = r.id;
            this.recForm = {
                task_name: r.task_name, description: r.description || '', frequency: r.frequency,
                day_of_month: r.day_of_month || 1, day_of_week: r.day_of_week || 0,
                priority: r.priority, assignee_id: r.assignee_id || '',
            };
            this.showRecModal = true;
        },

        async saveRec() {
            if (!this.recForm.task_name) { window.toast.warning('업무명을 입력하세요.'); return; }
            this.savingRec = true;
            try {
                const body = { ...this.recForm };
                if (!body.description) body.description = null;
                body.assignee_id = body.assignee_id ? parseInt(body.assignee_id) : null;
                if (body.frequency !== 'monthly') delete body.day_of_month;
                if (body.frequency !== 'weekly') delete body.day_of_week;
                if (this.editingRecId) {
                    await api.patch(`/recurring-tasks/${this.editingRecId}`, body);
                } else {
                    await api.post(`/projects/${this.recurringProject}/recurring-tasks`, body);
                }
                this.showRecModal = false;
                window.toast.success(this.editingRecId ? '수정되었습니다.' : '반복 업무가 등록되었습니다.');
                await this.loadRecurring();
            } catch (e) { window.toast.error(e.message); }
            finally { this.savingRec = false; }
        },

        async toggleRecActive(r) {
            try {
                await api.patch(`/recurring-tasks/${r.id}`, { is_active: !r.is_active });
                r.is_active = !r.is_active;
                window.toast.success(r.is_active ? '활성화되었습니다.' : '비활성화되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        async deleteRec(r) {
            if (!await window.confirmDialog(`"${r.task_name}" 반복 업무를 삭제하시겠습니까?`, { title: '반복 업무 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/recurring-tasks/${r.id}`);
                window.toast.success('삭제되었습니다.');
                await this.loadRecurring();
            } catch (e) { window.toast.error(e.message); }
        },

        /* ── 헬퍼 ── */
        getProjectTypeBadge(t) {
            const m = { outsourcing: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300', internal: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300', maintenance: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300' };
            return m[t] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
        },
        getProjectTypeLabel(t) {
            const m = { outsourcing: '외주', internal: '내부', maintenance: '유지보수' };
            return m[t] || t;
        },
        getFreqLabel(f) {
            const m = { daily: '매일', weekly: '매주', monthly: '매월' };
            return m[f] || f;
        },
        getDowLabel(d) { return ['월','화','수','목','금','토','일'][d] || ''; },
        getTeamName(teamId) {
            if (!teamId) return '';
            const t = (window._teams || []).find(tm => (tm.id || tm.team_id) === teamId);
            return t ? t.name : '팀';
        },
    };
}

// ============================================================
// [Phase 6] 클라이언트 포털 페이지 (비로그인, 토큰 기반)
// ============================================================

function clientPortalPage() {
    return {
        loading: true, token: '', data: null, error: null,
        activeTab: 'tasks',

        init() {
            const m = (window.location.hash || '').match(/^#\/portal\/([a-zA-Z0-9_-]+)/);
            if (m) { this.token = m[1]; this.load(); }
            else { this.error = '유효하지 않은 포털 링크입니다.'; this.loading = false; }
        },

        async load() {
            try { this.data = await api.get(`/portal/${this.token}/data`); }
            catch (e) { this.error = e.message || '포털 데이터를 불러올 수 없습니다.'; }
            finally { this.loading = false; }
        },

        get progress() { return Math.round(this.data?.progress_percent || 0); },
        get taskCount() { return this.data?.tasks?.length || 0; },
        get pendingFeedbackCount() { return this.data?.pending_feedbacks?.length || 0; },
        get reportCount() { return this.data?.reports?.length || 0; },
        getStatusBadge(s) { return CS.statusClass[s] || 'bg-gray-100 text-gray-600'; },
        getStatusLabel(s) { return CS.statusLabel[s] || s; },
    };
}

// ============================================================
// [Phase 6] 설정 페이지 (캘린더 연동)
// ============================================================

function settingsPage() {
    return {
        loading: true, calendarSyncs: [], connecting: false, syncing: {},

        async init() { await this.loadCalendarStatus(); },

        async loadCalendarStatus() {
            this.loading = true;
            try { this.calendarSyncs = await api.get('/calendar/status') || []; }
            catch { this.calendarSyncs = []; }
            finally { this.loading = false; }
        },

        async connectGoogle() {
            const clientId = window._googleClientId || '';
            if (!clientId) { window.toast.error('Google OAuth 설정이 필요합니다. 관리자에게 문의하세요.'); return; }
            const redirectUri = window.location.origin + '/api/v1/auth/google/callback';
            const scope = 'https://www.googleapis.com/auth/calendar';
            const url = `https://accounts.google.com/o/oauth2/v2/auth?client_id=${encodeURIComponent(clientId)}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=${encodeURIComponent(scope)}&access_type=offline&prompt=consent&state=calendar_connect`;
            const popup = window.open(url, 'google_calendar_auth', 'width=500,height=600');
            window._calendarAuthCallback = async (code) => {
                this.connecting = true;
                try {
                    await api.post('/calendar/connect', { provider: 'google', auth_code: code });
                    window.toast.success('Google Calendar 연동이 완료되었습니다.');
                    await this.loadCalendarStatus();
                } catch (e) { window.toast.error(e.message); }
                finally { this.connecting = false; }
            };
        },

        async disconnectCalendar(syncId) {
            if (!await window.confirmDialog('캘린더 연동을 해제하시겠습니까?', { title: '연동 해제', confirmText: '해제', danger: true })) return;
            try {
                await api.del(`/calendar/${syncId}`);
                window.toast.success('캘린더 연동이 해제되었습니다.');
                await this.loadCalendarStatus();
            } catch (e) { window.toast.error(e.message); }
        },

        async syncCalendar(syncId) {
            this.syncing[syncId] = true;
            try {
                const res = await api.post(`/calendar/${syncId}/sync`);
                window.toast.success(`${res.synced_count}건의 업무가 동기화되었습니다.`);
                await this.loadCalendarStatus();
            } catch (e) { window.toast.error(e.message); }
            finally { this.syncing[syncId] = false; }
        },

        getProviderLabel(p) { return { google: 'Google Calendar', outlook: 'Outlook' }[p] || p; },
    };
}

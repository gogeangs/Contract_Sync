// ============================================================
// Contract Sync v2 — Frontend Main JS
// ============================================================

// ============ 유틸리티 함수 ============

window.confirmDialog = function(message, { title = '확인', confirmText = '확인', cancelText = '취소', danger = false, requireInput = '' } = {}) {
    return new Promise((resolve) => {
        const backdrop = document.createElement('div');
        backdrop.className = 'fixed inset-0 z-[110] flex items-center justify-center bg-black bg-opacity-50 confirm-backdrop';
        const btnColor = danger === 'medium' ? 'bg-yellow-600 hover:bg-yellow-700' : danger ? 'bg-red-600 hover:bg-red-700' : 'bg-indigo-600 hover:bg-indigo-700';
        backdrop.innerHTML = `
            <div class="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-sm mx-4 p-6 transform transition-all">
                <h3 class="confirm-title text-lg font-semibold text-gray-800 dark:text-gray-100 mb-2"></h3>
                <p class="confirm-message text-sm text-gray-600 dark:text-gray-300 mb-4"></p>
                ${requireInput ? `<input type="text" class="confirm-input w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white mb-4 focus:ring-2 focus:ring-red-500" placeholder="">` : ''}
                <div class="flex justify-end gap-3">
                    <button class="confirm-cancel px-4 py-2 text-sm text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"></button>
                    <button class="confirm-ok px-4 py-2 text-sm text-white rounded-lg transition-colors ${btnColor}"></button>
                </div>
            </div>
        `;
        backdrop.querySelector('.confirm-title').textContent = title;
        backdrop.querySelector('.confirm-message').textContent = message;
        backdrop.querySelector('.confirm-cancel').textContent = cancelText;
        const okBtn = backdrop.querySelector('.confirm-ok');
        okBtn.textContent = confirmText;
        if (requireInput) {
            const input = backdrop.querySelector('.confirm-input');
            input.placeholder = `"${requireInput}" 입력`;
            okBtn.disabled = true;
            okBtn.classList.add('disabled:opacity-50');
            input.addEventListener('input', () => { okBtn.disabled = input.value !== requireInput; });
        }
        document.body.appendChild(backdrop);
        backdrop.querySelector('.confirm-cancel').addEventListener('click', () => { backdrop.remove(); resolve(false); });
        okBtn.addEventListener('click', () => { backdrop.remove(); resolve(true); });
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

    // CSV 내보내기 유틸 (#17)
    downloadCsv(prefix, header, rows) {
        const escape = v => { const s = String(v ?? ''); return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s; };
        const csv = '\uFEFF' + [header.map(escape).join(','), ...rows.map(r => r.map(escape).join(','))].join('\r\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        const d = new Date(); const ds = `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`;
        a.href = url; a.download = `${prefix}_${ds}.csv`; a.click();
        URL.revokeObjectURL(url);
    },
    /** DOMPurify sanitize wrapper (#21) */
    sanitize(html) {
        if (!html) return '';
        if (typeof DOMPurify !== 'undefined') return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
        return html;
    },
};

// ============ API 헬퍼 ============

const api = {
    async _fetch(method, url, body) {
        const opts = { method, headers: {}, credentials: 'include' };
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
        // 사이드바 그룹핑 (5차)
        sideGroup: { project: true, comm: true, manage: false, etc: false },
        // F-5: 코치마크/온보딩
        coachStep: 0,
        showCoachmark: false,
        coachSteps: [
            { target: 'dashboard', title: '대시보드', desc: '전체 프로젝트 현황과 업무 통계를 한눈에 확인하세요.' },
            { target: 'projects', title: '프로젝트 관리', desc: '프로젝트를 생성하고 업무를 배정할 수 있습니다.' },
            { target: 'chatbot', title: 'AI 어시스턴트', desc: '우하단 버튼으로 AI에게 업무를 질문하세요.' },
            { target: 'settings', title: '설정', desc: '프로필, 알림, 캘린더 연동 등을 설정합니다.' },
        ],

        // 프로필 드롭다운
        profileDropdown: false,

        // SSE (#4)
        _sseSource: null,

        // 글로벌 검색 (#11)
        showSearchPalette: false,
        searchQuery: '', searchResults: { projects: [], tasks: [], clients: [] },
        searchLoading: false, _searchTimer: null,
        recentSearches: JSON.parse(localStorage.getItem('cs_recent_searches') || '[]'),
        searchSelectedIdx: -1,

        // 모바일 더보기 (#12)
        moreMenuOpen: false,

        // 팀 생성 모달 (#13)
        showTeamCreateModal: false, teamCreateForm: { name: '', description: '' }, teamCreating: false,

        async init() {
            this.initDarkMode();
            try { await this.checkAuth(); } catch {}
            this.initRouter();
            this._initGlobalSearch();
            // checkAuth 후 비로그인 상태면 랜딩으로 강제 이동 (Alpine 반응성 보장)
            this.$nextTick(() => {
                if (!this.user && this.currentPage !== 'landing' && this.currentPage !== 'feedback' && this.currentPage !== 'feedbackPortal' && this.currentPage !== 'inviteAccept' && this.currentPage !== 'portal') {
                    this.currentPage = 'landing';
                    this.pageParams = {};
                    history.replaceState(null, '', '#/landing');
                }
            });
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
            } else if (path === '/activity') {
                this.currentPage = 'activity'; this.pageParams = {};
            } else if (path === '/notifications') {
                this.currentPage = 'notifications'; this.pageParams = {};
            } else if (path === '/team-settings') {
                this.currentPage = 'teamSettings'; this.pageParams = {};
            } else if (path === '/settings') {
                this.currentPage = 'settings'; this.pageParams = {};
            } else if (path === '/feedback-requests') {
                this.currentPage = 'feedbackRequests'; this.pageParams = {};
            } else if ((m = path.match(/^\/feedback-portal\/([a-zA-Z0-9_-]+)$/))) {
                this.currentPage = 'feedbackPortal'; this.pageParams = { token: m[1] };
            } else if (path === '/mcp') {
                this.currentPage = 'mcp'; this.pageParams = {};
            } else if (path === '/boards') {
                this.currentPage = 'boards'; this.pageParams = {};
            } else if ((m = path.match(/^\/boards\/post\/(\d+)$/))) {
                this.currentPage = 'boardPost'; this.pageParams = { postId: parseInt(m[1]) };
            } else if ((m = path.match(/^\/invite\/([a-zA-Z0-9_-]+)$/))) {
                this.currentPage = 'inviteAccept'; this.pageParams = { token: m[1] };
            } else if (path === '/my-tasks') {
                this.currentPage = 'myTasks'; this.pageParams = {};
            } else if (path === '/chat') {
                this.currentPage = 'chat'; this.pageParams = {};
            } else if ((m = path.match(/^\/chat\/(\d+)$/))) {
                this.currentPage = 'chat'; this.pageParams = { roomId: parseInt(m[1]) };
            } else if (path === '/attendance') {
                this.currentPage = 'attendance'; this.pageParams = {};
            } else if (path === '/team-attendance') {
                this.currentPage = 'teamAttendance'; this.pageParams = {};
            } else if (path === '/landing') {
                this.currentPage = 'landing'; this.pageParams = {};
            } else {
                this.currentPage = 'dashboard'; this.pageParams = {};
            }

            // 비로그인 시 공개 페이지 외에는 랜딩으로 강제 이동
            if (!this.user) {
                const publicPages = ['landing', 'feedback', 'feedbackPortal', 'inviteAccept', 'portal'];
                if (!publicPages.includes(this.currentPage)) {
                    this.currentPage = 'landing';
                    this.pageParams = {};
                    window.location.hash = '#/landing';
                }
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
                    window._loggedIn = true;
                    this.teams = data.teams || [];
                    window._teams = this.teams;
                    window._selectedTeamId = this.selectedTeamId;
                    this.loadUnreadCount();
                    if (!this._notifInterval) {
                        this._notifInterval = setInterval(() => { if (!document.hidden) this.loadUnreadCount(); }, 30000);
                    }
                    this._connectSSE();
                    // F-5: 신규 사용자 온보딩 코치마크 (1회)
                    if (!localStorage.getItem('cs_onboarded')) {
                        setTimeout(() => { this.showCoachmark = true; this.coachStep = 0; }, 2000);
                    }
                }
            } catch { /* ignore */ }
            finally { this.loading = false; }
        },

        // F-5: 코치마크 제어
        nextCoach() {
            if (this.coachStep < this.coachSteps.length - 1) this.coachStep++;
            else this.finishCoach();
        },
        prevCoach() { if (this.coachStep > 0) this.coachStep--; },
        finishCoach() { this.showCoachmark = false; localStorage.setItem('cs_onboarded', 'true'); },

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
                if (this.user) window.location.hash = '#/dashboard';
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
                if (this.user) window.location.hash = '#/dashboard';
            } catch (e) { this.formError = e.message; }
            finally { this.formLoading = false; }
        },

        async logout() {
            try {
                await fetch('/api/v1/auth/logout', { method: 'POST' });
                this.user = null; this.teams = []; this.notifications = []; this.unreadCount = 0;
                if (this._notifInterval) { clearInterval(this._notifInterval); this._notifInterval = null; }
                this._disconnectSSE();
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
            const typeMap = {
                'comment': ['comment', 'reply'],
                'mention': ['mention'],
                'task': ['status_change', 'assign', 'deadline', 'task'],
                'team': ['team', 'team_invite', 'team_role'],
            };
            const types = typeMap[this.notifFilter] || [this.notifFilter];
            return this.notifications.filter(n => types.includes(n.type));
        },

        // ---- 팀 ----
        switchTeam(teamId) {
            this.selectedTeamId = teamId || null;
            this.teamDropdown = false;
            window._selectedTeamId = this.selectedTeamId;
            window.dispatchEvent(new CustomEvent('team-switched', { detail: this.selectedTeamId }));
        },

        // ---- SSE 실시간 알림 (#4) ----
        _connectSSE() {
            if (this._sseSource) return;
            try {
                this._sseSource = new EventSource('/sse/notifications');
                this._sseNotifHandler = (e) => {
                    try {
                        const data = JSON.parse(e.data);
                        this.unreadCount++;
                        this.notifications.unshift(data);
                        window.toast.info(data.title || '새 알림이 있습니다');
                    } catch (err) { console.warn('SSE 알림 파싱 실패:', err); }
                };
                this._sseSource.addEventListener('notification', this._sseNotifHandler);
                this._sseSource.addEventListener('connected', () => {});
                this._sseSource.addEventListener('heartbeat', () => {});
                this._sseSource.onerror = () => {};
            } catch (err) { console.warn('SSE 연결 실패:', err); }
        },
        _disconnectSSE() {
            if (this._sseSource) {
                if (this._sseNotifHandler) this._sseSource.removeEventListener('notification', this._sseNotifHandler);
                this._sseSource.close();
                this._sseSource = null;
                this._sseNotifHandler = null;
            }
        },

        // ---- 알림 삭제 (#3) ----
        async deleteNotif(id) {
            try {
                await fetch(`/api/v1/notifications/${id}`, { method: 'DELETE' });
                const n = this.notifications.find(x => x.id === id);
                if (n && !n.is_read) this.unreadCount = Math.max(0, this.unreadCount - 1);
                this.notifications = this.notifications.filter(x => x.id !== id);
            } catch {}
        },

        notifLink(n) {
            if (!n.link) return;
            try {
                const link = typeof n.link === 'string' ? JSON.parse(n.link) : n.link;
                if (link.project_id) {
                    this.markNotifRead(n.id);
                    this.showNotifPanel = false;
                    this.navigate(`/projects/${link.project_id}`);
                }
            } catch {}
        },

        // ---- 글로벌 검색 / Ctrl+K (#11) ----
        _initGlobalSearch() {
            document.addEventListener('keydown', (e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                    e.preventDefault();
                    this.showSearchPalette = !this.showSearchPalette;
                    if (this.showSearchPalette) {
                        this.searchQuery = '';
                        this.searchResults = { projects: [], tasks: [], clients: [] };
                        this.searchSelectedIdx = -1;
                        this.$nextTick(() => { document.getElementById('globalSearchInput')?.focus(); });
                    }
                }
                if (e.key === 'Escape' && this.showSearchPalette) {
                    this.showSearchPalette = false;
                }
            });
        },

        onSearchInput() {
            clearTimeout(this._searchTimer);
            if (!this.searchQuery.trim()) {
                this.searchResults = { projects: [], tasks: [], clients: [] };
                return;
            }
            this._searchTimer = setTimeout(() => this._doSearch(), 300);
        },

        async _doSearch() {
            const q = this.searchQuery.trim();
            if (!q) return;
            this.searchLoading = true;
            try {
                const [pData, tData, cData] = await Promise.all([
                    api.get(`/projects?search=${encodeURIComponent(q)}&size=5`).catch(() => ({})),
                    api.get(`/tasks?search=${encodeURIComponent(q)}&size=5`).catch(() => ({})),
                    api.get(`/clients?search=${encodeURIComponent(q)}&size=5`).catch(() => ({})),
                ]);
                this.searchResults = {
                    projects: pData?.projects || [],
                    tasks: tData?.tasks || [],
                    clients: cData?.clients || [],
                };
                this.searchSelectedIdx = -1;
                // 저장 최근 검색
                const recent = this.recentSearches.filter(s => s !== q);
                recent.unshift(q);
                this.recentSearches = recent.slice(0, 5);
                localStorage.setItem('cs_recent_searches', JSON.stringify(this.recentSearches));
            } catch {}
            finally { this.searchLoading = false; }
        },

        get searchAllItems() {
            const items = [];
            for (const p of this.searchResults.projects) items.push({ type: 'project', id: p.id, name: p.project_name, sub: p.status });
            for (const t of this.searchResults.tasks) items.push({ type: 'task', id: t.id, name: t.task_name, sub: t.status, projectId: t.project_id });
            for (const c of this.searchResults.clients) items.push({ type: 'client', id: c.id, name: c.name, sub: c.category });
            return items;
        },

        searchNavigate(item) {
            this.showSearchPalette = false;
            if (item.type === 'project') this.navigate(`/projects/${item.id}`);
            else if (item.type === 'task') this.navigate('/tasks');
            else if (item.type === 'client') this.navigate(`/clients/${item.id}`);
        },

        searchKeyNav(e) {
            const items = this.searchAllItems;
            if (!items.length) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); this.searchSelectedIdx = Math.min(this.searchSelectedIdx + 1, items.length - 1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); this.searchSelectedIdx = Math.max(this.searchSelectedIdx - 1, 0); }
            else if (e.key === 'Enter' && this.searchSelectedIdx >= 0) { e.preventDefault(); this.searchNavigate(items[this.searchSelectedIdx]); }
        },

        // ---- 팀 생성 (#13) ----
        async createTeam() {
            if (!this.teamCreateForm.name.trim()) { window.toast.warning('팀 이름을 입력해주세요.'); return; }
            this.teamCreating = true;
            try {
                const team = await api.post('/teams', this.teamCreateForm);
                window.toast.success('팀이 생성되었습니다.');
                this.showTeamCreateModal = false;
                this.teamCreateForm = { name: '', description: '' };
                // 팀 목록 새로고침
                await this.checkAuth();
                this.switchTeam(team.id);
            } catch (e) { window.toast.error(e.message); }
            finally { this.teamCreating = false; }
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
        // Sprint 1 #2: 대시보드 고도화
        revenue: { months: [], amounts: [] },
        workload: [],
        insights: [],
        insightsLoading: false,
        revenueLoading: true,
        workloadLoading: true,
        // F-4: 오늘의 브리핑
        briefingDismissed: sessionStorage.getItem('cs_briefing_dismissed') === 'true',
        // F-6: 능동적 알림 카드
        proactiveAlerts: [],
        alertsDismissed: new Set(),

        get greeting() {
            const h = new Date().getHours();
            return h < 12 ? '좋은 아침이에요' : h < 18 ? '좋은 오후에요' : '좋은 저녁이에요';
        },

        briefingData: null,
        async loadBriefing() {
            try {
                this.briefingData = await api.get('/dashboard/briefing');
            } catch { this.briefingData = null; }
        },
        get briefingItems() {
            const items = [];
            // API 데이터 우선
            if (this.briefingData?.items) return this.briefingData.items;
            // API 미응답 시 stats 기반 폴백
            const due = this.stats?.pendingTasks || 0;
            if (due > 0) items.push({ icon: '⏰', text: `오늘 마감 업무 ${due}건이 있습니다`, color: 'text-red-600 dark:text-red-400', action: 'my-tasks' });
            const ip = this.stats?.inProgressTasks || 0;
            if (ip > 0) items.push({ icon: '🔄', text: `진행 중 업무 ${ip}건`, color: 'text-blue-600 dark:text-blue-400', action: 'tasks' });
            const proj = this.stats?.projects || 0;
            if (proj > 0) items.push({ icon: '📁', text: `활성 프로젝트 ${proj}개`, color: 'text-indigo-600 dark:text-indigo-400', action: 'projects' });
            // 데이터가 없어도 환영 메시지 표시
            if (items.length === 0) items.push({ icon: '👋', text: '오늘도 좋은 하루 되세요! 새 프로젝트를 시작해보세요.', color: 'text-white', action: 'projects' });
            return items;
        },

        dismissBriefing() { this.briefingDismissed = true; sessionStorage.setItem('cs_briefing_dismissed', 'true'); },
        // F-6: 능동적 알림 생성 (데이터 기반)
        buildProactiveAlerts() {
            const alerts = [];
            const due = this.stats?.pendingTasks || 0;
            if (due >= 3) alerts.push({ id: 'overdue', icon: '🔴', title: `마감 임박 업무 ${due}건`, desc: '우선순위를 확인하고 일정을 조정하세요.', action: '내 업무 보기', route: '/my-tasks', type: 'urgent' });
            const ip = this.stats?.inProgressTasks || 0;
            if (ip >= 5) alerts.push({ id: 'busy', icon: '⚡', title: `진행 중 업무가 ${ip}건입니다`, desc: '업무 부하가 높습니다. 우선순위를 조정해보세요.', action: '업무 목록', route: '/tasks', type: 'warning' });
            this.proactiveAlerts = alerts.filter(a => !this.alertsDismissed.has(a.id));
        },
        dismissAlert(id) { this.alertsDismissed.add(id); this.proactiveAlerts = this.proactiveAlerts.filter(a => a.id !== id); },

        async init() {
            await Promise.all([this.load(), this.loadBriefing()]);
            this.buildProactiveAlerts();
            this.$el.addEventListener('route-changed', () => { if (this.$data.currentPage === 'dashboard') { this.load(); this.loadBriefing(); } });
        },

        async load() {
            try { await api.get('/auth/me'); } catch { this.loading = false; return; }
            this.loading = true;
            this.revenueLoading = true;
            this.workloadLoading = true;
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
            } catch {}
            finally { this.loading = false; }

            // 매출 + 워크로드 병렬 로드
            Promise.all([
                api.get('/dashboard/revenue').then(d => { this.revenue = d || { months: [], amounts: [] }; }).catch(() => {}),
                api.get('/dashboard/workload').then(d => { this.workload = d || []; }).catch(() => {}),
            ]).finally(() => { this.revenueLoading = false; this.workloadLoading = false; });
        },

        async loadInsights() {
            this.insightsLoading = true;
            try {
                this.insights = await api.get('/dashboard/ai-insights') || [];
            } catch { this.insights = []; }
            finally { this.insightsLoading = false; }
        },

        // 매출 차트 헬퍼
        get revenueMax() {
            return Math.max(...(this.revenue.amounts || [0]), 1);
        },
        barHeight(amount) {
            return Math.max((amount / this.revenueMax) * 100, 2);
        },
        formatAmount(n) {
            if (n >= 10000) return (n / 10000).toFixed(0) + '만';
            if (n >= 1000) return (n / 1000).toFixed(0) + '천';
            return n.toLocaleString();
        },

        // 워크로드 헬퍼
        workloadPercent(item) {
            if (!item.task_count) return 0;
            return Math.round((item.completed_count / item.task_count) * 100);
        },
        workloadColor(item) {
            const pct = this.workloadPercent(item);
            if (pct >= 80) return 'bg-green-500';
            if (pct >= 50) return 'bg-blue-500';
            return 'bg-orange-500';
        },

        // 인사이트 헬퍼
        insightIcon(type) {
            if (type === 'warning') return 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z';
            if (type === 'suggestion') return 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z';
            return 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z';
        },
        insightColor(type) {
            if (type === 'warning') return 'text-orange-500 bg-orange-100 dark:bg-orange-900/30';
            if (type === 'suggestion') return 'text-green-500 bg-green-100 dark:bg-green-900/30';
            return 'text-blue-500 bg-blue-100 dark:bg-blue-900/30';
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
        showCreateModal: false,
        saving: false,
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

        async confirmDelete(client) {
            if (!await window.confirmDialog(`"${client.name}"을(를) 삭제하시겠습니까? 관련 데이터도 함께 삭제됩니다.`, { title: '발주처 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/clients/${client.id}`);
                window.toast.success('발주처가 삭제되었습니다.');
                await this.loadClients();
            } catch (e) { window.toast.error(e.message); }
        },

        doSearch: debounce(function() { this.page = 1; this.loadClients(); }, 300),

        get totalPages() { return Math.ceil(this.total / this.size) || 1; },

        goPage(p) { if (p >= 1 && p <= this.totalPages) { this.page = p; this.loadClients(); } },

        exportCsv() {
            const header = ['발주처명','담당자','연락처','이메일'];
            const rows = this.clients.map(c => [c.name, c.contact_name || '', c.contact_phone || '', c.contact_email || '']);
            window.CS.downloadCsv('clients', header, rows);
        },
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

        exportCsv() {
            const header = ['프로젝트명','발주처','상태','시작일','마감일','계약금액'];
            const rows = this.projects.map(p => [p.project_name, p.client_name || '', CS.statusLabel[p.status] || p.status, p.start_date || '', p.end_date || '', p.contract_amount || '']);
            window.CS.downloadCsv('projects', header, rows);
        },
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
        showFeedbackRequestModal: false, fbReqSending: false,
        fbReqForm: { recipient_email: '', subject: '', message: '', feedback_deadline: '', channel: 'email' },
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

        // 댓글 (#6, #7)
        commentList: [], commentContent: '', replyTo: null, replyContent: '', commentLoading: false,
        mentionSearch: '', mentionResults: [], showMentionDropdown: false, mentionIdx: -1,
        _commentObserver: null,

        async loadComments(taskId) {
            this.commentLoading = true;
            try {
                let url = `/${this.project.id}/comments`;
                if (taskId) url += `?task_id=${taskId}`;
                this.commentList = await api.get(url) || [];
            } catch { this.commentList = []; }
            finally { this.commentLoading = false; }
        },

        async submitComment(taskId) {
            if (!this.commentContent.trim()) return;
            try {
                await api.post(`/${this.project.id}/comments`, {
                    content: this.commentContent.trim(),
                    task_id: taskId || null,
                });
                this.commentContent = '';
                await this.loadComments(taskId);
                window.toast.success('댓글이 등록되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        startReply(comment) {
            this.replyTo = comment.id;
            this.replyContent = '';
        },

        cancelReply() {
            this.replyTo = null;
            this.replyContent = '';
        },

        async submitReply(taskId) {
            if (!this.replyContent.trim()) return;
            try {
                await api.post(`/${this.project.id}/comments`, {
                    content: this.replyContent.trim(),
                    task_id: taskId || null,
                    parent_id: this.replyTo,
                });
                this.replyTo = null;
                this.replyContent = '';
                await this.loadComments(taskId);
            } catch (e) { window.toast.error(e.message); }
        },

        async deleteComment(commentId, taskId) {
            if (!await window.confirmDialog('댓글을 삭제하시겠습니까?', { title: '댓글 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/${this.project.id}/comments/${commentId}`);
                await this.loadComments(taskId);
            } catch (e) { window.toast.error(e.message); }
        },

        async markCommentRead(commentId) {
            try {
                await api.post(`/${this.project.id}/comments/${commentId}/read`, {});
            } catch {}
        },

        // @멘션 (#8)
        onCommentInput(e, field) {
            const val = this[field];
            const cursor = e.target.selectionStart;
            const before = val.substring(0, cursor);
            const atMatch = before.match(/@([^\s@]*)$/);
            if (atMatch && this.project?.team_id) {
                this.mentionSearch = atMatch[1].toLowerCase();
                this._loadMentionCandidates();
                this.showMentionDropdown = true;
            } else {
                this.showMentionDropdown = false;
            }
        },

        async _loadMentionCandidates() {
            if (!this._teamMembers) {
                try {
                    const team = await api.get(`/teams/${this.project.team_id}`);
                    this._teamMembers = team?.members || [];
                } catch { this._teamMembers = []; }
            }
            this.mentionResults = this._teamMembers.filter(m =>
                (m.name || '').toLowerCase().includes(this.mentionSearch) ||
                (m.email || '').toLowerCase().includes(this.mentionSearch)
            ).slice(0, 5);
            this.mentionIdx = -1;
        },

        insertMention(member, field, inputEl) {
            const val = this[field];
            const cursor = inputEl.selectionStart;
            const before = val.substring(0, cursor);
            const after = val.substring(cursor);
            const newBefore = before.replace(/@([^\s@]*)$/, `@[${member.name || member.email}](${member.email}) `);
            this[field] = newBefore + after;
            this.showMentionDropdown = false;
            this.$nextTick(() => {
                inputEl.focus();
                inputEl.selectionStart = inputEl.selectionEnd = newBefore.length;
            });
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
            if (!await window.confirmDialog('포털 링크를 비활성화하시겠습니까? 발주처가 더 이상 접근할 수 없습니다.', { title: '포털 링크 비활성화', confirmText: '비활성화', danger: 'medium' })) return;
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

        // 피드백 요청 (S4-6)
        async sendFeedbackRequest() {
            if (!this.fbReqForm.recipient_email || !this.fbReqForm.subject) {
                window.toast.warning('수신자 이메일과 제목을 입력해주세요.');
                return;
            }
            this.fbReqSending = true;
            try {
                await api.post(`/projects/${this.project.id}/feedback-request`, this.fbReqForm);
                this.showFeedbackRequestModal = false;
                this.fbReqForm = { recipient_email: '', subject: '', message: '', feedback_deadline: '' };
                window.toast.success('피드백 요청이 발송되었습니다.');
            } catch (e) { window.toast.error(e.message || '발송 실패'); }
            finally { this.fbReqSending = false; }
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

        // 일괄 작업 (#19)
        selectedTaskIds: [],
        bulkAction: '', bulkValue: '',

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

        // 일괄 작업 (#19)
        toggleTaskSelection(taskId) {
            const idx = this.selectedTaskIds.indexOf(taskId);
            if (idx >= 0) this.selectedTaskIds.splice(idx, 1);
            else this.selectedTaskIds.push(taskId);
        },
        get allSelected() { return this.tasks.length > 0 && this.selectedTaskIds.length === this.tasks.length; },
        toggleSelectAll() {
            if (this.allSelected) this.selectedTaskIds = [];
            else this.selectedTaskIds = this.tasks.map(t => t.id);
        },
        async bulkStatusChange(status) {
            try {
                await api.patch('/tasks/bulk', { task_ids: this.selectedTaskIds, action: 'status_change', value: status });
                window.toast.success(`${this.selectedTaskIds.length}건 상태 변경 완료`);
                this.selectedTaskIds = [];
                await this.loadTasks();
            } catch (e) { window.toast.error(e.message); }
        },
        async bulkDelete() {
            if (!await window.confirmDialog(`${this.selectedTaskIds.length}건의 업무를 삭제하시겠습니까?`, { title: '일괄 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.patch('/tasks/bulk', { task_ids: this.selectedTaskIds, action: 'delete' });
                window.toast.success(`${this.selectedTaskIds.length}건 삭제 완료`);
                this.selectedTaskIds = [];
                await this.loadTasks();
            } catch (e) { window.toast.error(e.message); }
        },

        // CSV 내보내기 (#17)
        exportCsv() {
            const header = ['업무명','프로젝트','담당자','상태','마감일','우선순위'];
            const statusMap = { pending: '대기', in_progress: '진행중', completed: '완료', feedback_pending: '피드백 대기', confirmed: '확인', revision_requested: '수정 요청' };
            const rows = this.tasks.map(t => [t.task_name, t.project_name || '', t.assignee_name || '', statusMap[t.status] || t.status, t.due_date || '', t.priority]);
            window.CS.downloadCsv('tasks', header, rows);
        },
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
        _quill: null,

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
            this.$nextTick(() => this._initQuill());
        },

        _initQuill() {
            if (this._quill) { this._quill.root.innerHTML = this.form.body_html || ''; return; }
            const el = this.$refs.quillEditor;
            if (!el || typeof Quill === 'undefined') return;
            this._quill = new Quill(el, {
                theme: 'snow',
                placeholder: '보고 내용을 작성하세요...',
                modules: {
                    toolbar: [
                        ['bold', 'italic', 'underline'],
                        [{ list: 'ordered' }, { list: 'bullet' }],
                        ['link', 'image'],
                        ['clean'],
                    ],
                },
            });
            if (this.form.body_html) this._quill.root.innerHTML = this.form.body_html;
            this._quill.on('text-change', () => { this.form.body_html = this._quill.root.innerHTML; });
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
                if (res.body_html) {
                    this.form.body_html = res.body_html;
                    if (this._quill) this._quill.root.innerHTML = res.body_html;
                }
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

// (settingsPage 이동됨 — Sprint 5 #15 확장 버전으로 교체)

// ============================================================
//  활동 로그 페이지 — Sprint 1 #1
// ============================================================

function activityPage() {
    return {
        items: [], total: 0, page: 1, size: 30,
        loading: true, hasMore: false,
        filterProject: '', filterTeam: '',
        filterAction: '',
        projects: [], teams: [],

        async init() {
            await Promise.all([this.load(), this.loadFilters()]);
        },

        async load() {
            this.loading = true;
            try {
                let url = `/activity?page=${this.page}&size=${this.size}`;
                if (this.filterProject) url += `&project_id=${this.filterProject}`;
                if (this.filterTeam) url += `&team_id=${this.filterTeam}`;
                const data = await api.get(url);
                const newItems = data?.items || [];
                if (this.page === 1) {
                    this.items = newItems;
                } else {
                    this.items = [...this.items, ...newItems];
                }
                this.total = data?.total || 0;
                this.hasMore = this.items.length < this.total;
            } catch (e) { window.toast.error('활동 로그를 불러올 수 없습니다.'); }
            finally { this.loading = false; }
        },

        async loadMore() {
            this.page++;
            await this.load();
        },

        async applyFilter() {
            this.page = 1;
            await this.load();
        },

        resetFilter() {
            this.filterProject = '';
            this.filterTeam = '';
            this.filterAction = '';
            this.page = 1;
            this.load();
        },

        async loadFilters() {
            try {
                const [pData, tData] = await Promise.all([
                    api.get('/projects?page=1&size=100'),
                    api.get('/teams').catch(() => ({ teams: [] })),
                ]);
                this.projects = pData?.projects || [];
                this.teams = tData?.teams || tData || [];
            } catch {}
        },

        get filteredItems() {
            if (!this.filterAction) return this.items;
            return this.items.filter(i => i.action === this.filterAction);
        },

        get groupedByDate() {
            const groups = [];
            let currentLabel = null;
            const today = new Date(); today.setHours(0,0,0,0);
            const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);

            for (const item of this.filteredItems) {
                const d = new Date(item.created_at);
                const day = new Date(d); day.setHours(0,0,0,0);
                let label;
                if (day.getTime() === today.getTime()) label = '오늘';
                else if (day.getTime() === yesterday.getTime()) label = '어제';
                else {
                    const dow = ['일','월','화','수','목','금','토'][day.getDay()];
                    label = `${day.getMonth()+1}월 ${day.getDate()}일 (${dow})`;
                }
                if (label !== currentLabel) {
                    groups.push({ label, items: [] });
                    currentLabel = label;
                }
                groups[groups.length - 1].items.push(item);
            }
            return groups;
        },

        formatTime(iso) {
            const d = new Date(iso);
            const today = new Date(); today.setHours(0,0,0,0);
            const day = new Date(d); day.setHours(0,0,0,0);
            const hh = String(d.getHours()).padStart(2,'0');
            const mm = String(d.getMinutes()).padStart(2,'0');
            if (day.getTime() === today.getTime()) return `${hh}:${mm}`;
            return `${d.getMonth()+1}월 ${d.getDate()}일 ${hh}:${mm}`;
        },

        actionMessage(item) {
            const map = {
                'create:project': `'${item.target_name}' 프로젝트를 생성했습니다`,
                'create:task': `'${item.target_name}' 업무를 생성했습니다`,
                'update:project': `'${item.target_name}' 프로젝트를 수정했습니다`,
                'update:task': `'${item.target_name}' 업무를 수정했습니다`,
                'status_change:task': `'${item.target_name}' 업무 상태를 변경했습니다`,
                'comment:task': `'${item.target_name}' 업무에 댓글을 남겼습니다`,
                'comment:project': `'${item.target_name}' 프로젝트에 댓글을 남겼습니다`,
                'assign:task': `'${item.target_name}' 업무를 할당했습니다`,
                'delete:task': `'${item.target_name}' 업무를 삭제했습니다`,
                'delete:project': `'${item.target_name}' 프로젝트를 삭제했습니다`,
                'create:client': `'${item.target_name}' 발주처를 등록했습니다`,
                'update:client': `'${item.target_name}' 발주처를 수정했습니다`,
                'invite:member': `'${item.target_name}'님을 팀에 초대했습니다`,
                'remove:member': `'${item.target_name}'님을 팀에서 제거했습니다`,
            };
            return map[`${item.action}:${item.target_type}`] || `'${item.target_name}'에 대해 ${item.action} 작업을 수행했습니다`;
        },

        actionIcon(action) {
            const icons = {
                create: 'M12 4v16m8-8H4',
                update: 'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z',
                status_change: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
                comment: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z',
                assign: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z',
                delete: 'M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16',
                invite: 'M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z',
                remove: 'M13 7a4 4 0 11-8 0 4 4 0 018 0zM9 14a6 6 0 00-6 6v1h12v-1a6 6 0 00-6-6zM21 12h-6',
            };
            return icons[action] || icons.update;
        },

        actionColor(action) {
            const colors = {
                create: 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400',
                update: 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400',
                status_change: 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400',
                comment: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-600 dark:text-yellow-400',
                assign: 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400',
                delete: 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400',
                invite: 'bg-teal-100 dark:bg-teal-900/30 text-teal-600 dark:text-teal-400',
                remove: 'bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400',
            };
            return colors[action] || colors.update;
        },

        userInitial(name) {
            return (name || '?').charAt(0).toUpperCase();
        },
    };
}

// ============================================================
//  전체 알림 페이지 — Sprint 2 #3
// ============================================================

function notificationsPage() {
    return {
        items: [], total: 0, page: 1, size: 20,
        loading: true, filter: 'all', unreadOnly: false,

        async init() { await this.load(); },

        async load() {
            this.loading = true;
            try {
                let url = `/notifications?page=${this.page}&size=${this.size}`;
                if (this.unreadOnly) url += '&unread_only=true';
                const data = await api.get(url);
                this.items = data?.items || [];
                this.total = data?.total || this.items.length;
            } catch { this.items = []; }
            finally { this.loading = false; }
        },

        get filteredItems() {
            if (this.filter === 'all') return this.items;
            const typeMap = { comment: ['comment','reply'], mention: ['mention'], task: ['status_change','assign','deadline','task'], team: ['team','team_invite','team_role'] };
            const types = typeMap[this.filter] || [];
            return this.items.filter(n => types.includes(n.type));
        },

        async markRead(n) {
            if (n.is_read) return;
            try { await api.patch(`/notifications/${n.id}/read`); n.is_read = true; } catch {}
        },

        async markAllRead() {
            try { await api.patch('/notifications/read-all'); this.items.forEach(n => n.is_read = true); } catch {}
        },

        async deleteNotif(id) {
            try { await api.del(`/notifications/${id}`); this.items = this.items.filter(n => n.id !== id); } catch {}
        },

        goLink(n) {
            this.markRead(n);
            try {
                const link = typeof n.link === 'string' ? JSON.parse(n.link) : n.link;
                if (link?.project_id) window.location.hash = `#/projects/${link.project_id}`;
            } catch {}
        },

        setFilter(f) { this.filter = f; },
        toggleUnread() { this.unreadOnly = !this.unreadOnly; this.page = 1; this.load(); },

        get totalPages() { return Math.ceil(this.total / this.size) || 1; },
        goPage(p) { if (p >= 1 && p <= this.totalPages) { this.page = p; this.load(); } },
    };
}

// ============================================================
//  팀 설정 페이지 — Sprint 5 #13
// ============================================================

function teamSettingsPage() {
    return {
        team: null, members: [], loading: true,
        editName: '', editDesc: '', saving: false,
        showInviteModal: false, inviteEmail: '', inviting: false,

        async init() {
            const teamId = window._selectedTeamId;
            if (!teamId) { window.toast.warning('팀을 먼저 선택해주세요.'); window.location.hash = '#/dashboard'; return; }
            await this.load(teamId);
        },

        async load(teamId) {
            this.loading = true;
            try {
                const data = await api.get(`/teams/${teamId}`);
                this.team = data;
                this.members = data?.members || [];
                this.editName = data?.name || '';
                this.editDesc = data?.description || '';
            } catch (e) { window.toast.error('팀 정보를 불러올 수 없습니다.'); }
            finally { this.loading = false; }
        },

        async saveName() {
            this.saving = true;
            try {
                await api.patch(`/teams/${this.team.id}`, { name: this.editName });
                this.team.name = this.editName;
                window.toast.success('팀 이름이 변경되었습니다.');
            } catch (e) { window.toast.error(e.message); }
            finally { this.saving = false; }
        },

        async saveDesc() {
            this.saving = true;
            try {
                await api.patch(`/teams/${this.team.id}`, { description: this.editDesc });
                this.team.description = this.editDesc;
                window.toast.success('팀 설명이 변경되었습니다.');
            } catch (e) { window.toast.error(e.message); }
            finally { this.saving = false; }
        },

        async inviteMember() {
            if (!this.inviteEmail.trim()) return;
            this.inviting = true;
            try {
                await api.post(`/teams/${this.team.id}/members`, { email: this.inviteEmail.trim() });
                window.toast.success('멤버가 초대되었습니다.');
                this.inviteEmail = '';
                this.showInviteModal = false;
                await this.load(this.team.id);
            } catch (e) { window.toast.error(e.message); }
            finally { this.inviting = false; }
        },

        async changeRole(member, newRole) {
            try {
                await api.patch(`/teams/${this.team.id}/members/${member.user_id}/role`, { role: newRole });
                member.role = newRole;
                window.toast.success('역할이 변경되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        async removeMember(member) {
            if (!await window.confirmDialog(`${member.name || member.email}님을 팀에서 제거하시겠습니까?`, { title: '멤버 제거', confirmText: '제거', danger: true })) return;
            try {
                await api.del(`/teams/${this.team.id}/members/${member.user_id}`);
                this.members = this.members.filter(m => m.user_id !== member.user_id);
                window.toast.success('멤버가 제거되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        async deleteTeam() {
            if (!await window.confirmDialog('이 작업은 되돌릴 수 없습니다. 모든 팀 데이터가 영구 삭제됩니다. 확인하려면 팀 이름을 입력하세요.', { title: '팀 삭제', confirmText: '영구 삭제', danger: true, requireInput: this.team.name })) return;
            try {
                await api.del(`/teams/${this.team.id}`);
                window.toast.success('팀이 삭제되었습니다.');
                window.location.hash = '#/dashboard';
            } catch (e) { window.toast.error(e.message); }
        },

        roleLabel(r) { return { owner: '소유자', admin: '관리자', member: '멤버', viewer: '뷰어' }[r] || r; },
        roleBadge(r) { return { owner: 'bg-yellow-100 text-yellow-800', admin: 'bg-blue-100 text-blue-700', member: 'bg-gray-100 text-gray-600', viewer: 'bg-green-100 text-green-700' }[r] || 'bg-gray-100 text-gray-600'; },
    };
}

// ============================================================
//  설정 페이지 확장 — Sprint 5 #15
// ============================================================

function settingsPage() {
    return {
        activeSettingsTab: 'profile',
        // 프로필
        profileName: '', profileSaving: false,
        profilePicture: null, picturePreview: null, pictureUploading: false,
        // 보안
        currentPassword: '', newPassword: '', newPasswordConfirm: '', passwordSaving: false, passwordError: '',
        // 알림 설정 (localStorage)
        notifSettings: JSON.parse(localStorage.getItem('cs_notif_settings') || '{"comment":true,"mention":true,"status_change":true,"deadline":true,"weekly_report":true}'),
        // 캘린더
        calendarSyncs: [], loading: true, connecting: false, syncing: {},
        connectDirection: 'cs_to_google',

        async init() {
            try {
                const me = await api.get('/auth/me');
                this.profileName = me?.user?.name || '';
                this.profilePicture = me?.user?.picture || null;
            } catch {}
            await this.loadCalendarSyncs();
        },

        // 프로필
        async saveProfile() {
            this.profileSaving = true;
            try {
                await api.patch('/auth/profile', { name: this.profileName });
                window.toast.success('프로필이 저장되었습니다.');
            } catch (e) { window.toast.error(e.message); }
            finally { this.profileSaving = false; }
        },

        // 프로필 이미지
        previewImage(ev) {
            const file = ev.target.files[0];
            if (!file) return;
            if (file.size > 2 * 1024 * 1024) { window.toast.error('이미지 크기는 2MB 이하여야 합니다.'); return; }
            this.picturePreview = URL.createObjectURL(file);
        },

        async uploadPicture(ev) {
            const file = ev.target?.files?.[0] || this.$refs.pictureInput?.files?.[0];
            if (!file) return;
            this.pictureUploading = true;
            try {
                const fd = new FormData();
                fd.append('file', file);
                const res = await api._fetch('/auth/profile/picture', { method: 'POST', body: fd, rawBody: true });
                this.profilePicture = res?.picture;
                this.picturePreview = null;
                window.toast.success('프로필 이미지가 변경되었습니다.');
            } catch (e) { window.toast.error(e.message); }
            finally { this.pictureUploading = false; }
        },

        async deletePicture() {
            if (!await window.confirmDialog('프로필 이미지를 삭제하시겠습니까?', { title: '이미지 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del('/auth/profile/picture');
                this.profilePicture = null;
                this.picturePreview = null;
                window.toast.success('프로필 이미지가 삭제되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        // 비밀번호 변경
        async changePassword() {
            this.passwordError = '';
            if (!this.currentPassword || !this.newPassword || !this.newPasswordConfirm) { this.passwordError = '모든 필드를 입력해주세요.'; return; }
            if (this.newPassword !== this.newPasswordConfirm) { this.passwordError = '새 비밀번호가 일치하지 않습니다.'; return; }
            if (this.newPassword.length < 8) { this.passwordError = '비밀번호는 8자 이상이어야 합니다.'; return; }
            this.passwordSaving = true;
            try {
                await api.patch('/auth/password', { current_password: this.currentPassword, new_password: this.newPassword, new_password_confirm: this.newPasswordConfirm });
                window.toast.success('비밀번호가 변경되었습니다.');
                this.currentPassword = ''; this.newPassword = ''; this.newPasswordConfirm = '';
            } catch (e) { this.passwordError = e.message; }
            finally { this.passwordSaving = false; }
        },

        // 알림 설정
        toggleNotifSetting(key) {
            this.notifSettings[key] = !this.notifSettings[key];
            localStorage.setItem('cs_notif_settings', JSON.stringify(this.notifSettings));
        },

        // 캘린더 — 5차 개발: 양방향 동기화 지원
        async loadCalendarSyncs() {
            this.loading = true;
            try { this.calendarSyncs = await api.get('/calendar/status') || []; } catch { this.calendarSyncs = []; }
            finally { this.loading = false; }
        },
        async connectGoogle() {
            this.connecting = true;
            try {
                const data = await api.post('/calendar/connect', { provider: 'google', auth_code: '', sync_direction: this.connectDirection });
                if (data?.auth_url) window.location.href = data.auth_url;
                else { await this.loadCalendarSyncs(); window.toast.success('Google Calendar 연동 완료'); }
            } catch (e) { window.toast.error(e.message); }
            finally { this.connecting = false; }
        },
        async disconnectCalendar(syncId) {
            if (!await window.confirmDialog('캘린더 연동을 해제하시겠습니까? 언제든 다시 연동할 수 있습니다.', { title: '연동 해제', confirmText: '해제', danger: 'medium' })) return;
            try {
                await api.del(`/calendar/${syncId}`);
                this.calendarSyncs = this.calendarSyncs.filter(s => s.id !== syncId);
                window.toast.success('연동이 해제되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },
        async syncCalendar(syncId) {
            this.syncing[syncId] = true;
            try {
                await api.post(`/calendar/${syncId}/sync`, {});
                window.toast.success('동기화가 완료되었습니다.');
                await this.loadCalendarSyncs();
            } catch (e) { window.toast.error(e.message); }
            finally { this.syncing[syncId] = false; }
        },
        async changeSyncDirection(syncId, direction) {
            try {
                await api.patch(`/calendar/${syncId}/direction`, { sync_direction: direction });
                const s = this.calendarSyncs.find(c => c.id === syncId);
                if (s) s.sync_direction = direction;
                window.toast.success('동기화 방향이 변경되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },
        getProviderLabel(p) { return { google: 'Google Calendar', outlook: 'Outlook' }[p] || p; },
        getDirectionLabel(d) { return { cs_to_google: 'CS → Google', google_to_cs: 'Google → CS', bidirectional: '양방향' }[d] || d; },
    };
}

// ============ 3차 개발: AI 챗봇 위젯 (S2-1~S2-7) ============

function chatbotWidget() {
    return {
        open: false,
        fullscreen: false,
        showSessions: false,
        showGreeting: false,
        // F-8: 자연어 명령 확인
        pendingAction: null,
        messages: [],
        sessions: [],
        currentSessionId: null,
        input: '',
        sending: false,
        streaming: false,
        presets: [],
        quickPresets: [],
        loading: true,
        loggedIn: false,

        async init() {
            // 메인 앱의 checkAuth 완료를 기다림 (최대 3초)
            for (let i = 0; i < 30; i++) {
                if (window._loggedIn) break;
                await new Promise(r => setTimeout(r, 100));
            }
            this.loggedIn = !!window._loggedIn;
            if (this.loggedIn) await this.loadPresets();
            this.loading = false;
            // 자동 인사 말풍선 (첫 방문 시 1회, 3초 후)
            if (this.loggedIn && !localStorage.getItem('cs_chatbot_greeted')) {
                setTimeout(() => { if (!this.open) this.showGreeting = true; }, 3000);
            }
        },

        dismissGreeting() {
            this.showGreeting = false;
            localStorage.setItem('cs_chatbot_greeted', 'true');
        },

        toggle() {
            this.open = !this.open;
            if (this.showGreeting) this.dismissGreeting();
            if (this.open && this.sessions.length === 0) this.loadSessions();
        },

        async loadPresets() {
            try {
                const res = await api.get('/chatbot/presets');
                const all = res?.presets || [];
                this.presets = all.slice(0, 6);
                this.quickPresets = all.slice(0, 4);
            } catch { this.presets = []; this.quickPresets = []; }
        },

        async loadSessions() {
            try {
                const data = await api.get('/chatbot/history');
                this.sessions = data?.sessions || [];
            } catch { this.sessions = []; }
        },

        async loadSession(sessionId) {
            this.currentSessionId = sessionId;
            this.showSessions = false;
            try {
                const data = await api.get(`/chatbot/history?session_id=${sessionId}`);
                this.messages = (data?.messages || []).map(m => ({
                    role: m.role,
                    content: m.content,
                    time: m.created_at,
                }));
            } catch { this.messages = []; }
            this.$nextTick(() => this.scrollBottom());
        },

        newSession() {
            this.currentSessionId = null;
            this.messages = [];
            this.showSessions = false;
        },

        async deleteSession(sessionId) {
            try {
                await api.del(`/chatbot/sessions/${sessionId}`);
                this.sessions = this.sessions.filter(s => s.id !== sessionId);
                if (this.currentSessionId === sessionId) this.newSession();
            } catch {}
        },

        sendPreset(preset) {
            this.input = preset.query || preset.text;
            this.send();
        },

        async send() {
            const msg = this.input.trim();
            if (!msg || this.sending) return;
            this.input = '';
            this.messages.push({ role: 'user', content: msg, time: new Date().toISOString() });
            this.$nextTick(() => this.scrollBottom());

            this.sending = true;
            this.streaming = true;
            const aiMsg = { role: 'assistant', content: '', time: new Date().toISOString() };
            this.messages.push(aiMsg);
            const aiIdx = this.messages.length - 1;

            try {
                const res = await fetch('/api/v1/chatbot/message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: msg, chat_session_id: this.currentSessionId }),
                });

                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    this.messages[aiIdx].content = err.detail || '오류가 발생했습니다.';
                    this.sending = false; this.streaming = false;
                    return;
                }

                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });

                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (data.type === 'chunk') {
                                    this.messages[aiIdx].content += data.content;
                                    this.$nextTick(() => this.scrollBottom());
                                } else if (data.type === 'done') {
                                    if (data.session_id) this.currentSessionId = data.session_id;
                                } else if (data.type === 'action_confirm') {
                                    // F-8: 자연어 명령 확인 카드
                                    this.pendingAction = data;
                                    this.$nextTick(() => this.scrollBottom());
                                } else if (data.type === 'error') {
                                    this.messages[aiIdx].content = data.content || '오류가 발생했습니다.';
                                }
                            } catch {}
                        }
                    }
                }
            } catch (e) {
                this.messages[aiIdx].content = '네트워크 오류가 발생했습니다.';
            } finally {
                this.sending = false;
                this.streaming = false;
            }
        },

        // F-8: 자연어 명령 확인/거절
        async confirmAction() {
            if (!this.pendingAction) return;
            const action = this.pendingAction;
            this.pendingAction = null;
            this.messages.push({ role: 'user', content: `✅ "${action.action_label || '실행'}" 확인`, time: new Date().toISOString() });
            try {
                const res = await api.post(action.endpoint, action.payload || {});
                this.messages.push({ role: 'assistant', content: res?.message || '명령이 실행되었습니다.', time: new Date().toISOString() });
            } catch (e) {
                this.messages.push({ role: 'assistant', content: `실행 실패: ${e.message}`, time: new Date().toISOString() });
            }
            this.$nextTick(() => this.scrollBottom());
        },

        cancelAction() {
            this.pendingAction = null;
            this.messages.push({ role: 'assistant', content: '명령이 취소되었습니다.', time: new Date().toISOString() });
            this.$nextTick(() => this.scrollBottom());
        },

        scrollBottom() {
            const el = this.$refs.chatMessages;
            if (el) el.scrollTop = el.scrollHeight;
        },

        formatTime(t) {
            if (!t) return '';
            const d = new Date(t);
            return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
        },

        formatSessionDate(t) {
            if (!t) return '';
            return new Date(t).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        },
    };
}

// ============ 3차 개발: Figma 탭 (S3-4) ============

function figmaTabComponent() {
    return {
        files: [],
        urls: [],
        loading: true,
        showAddModal: false,
        newUrl: '',
        adding: false,
        selectedFile: null,
        screenshots: {},

        async init() {
            await this.load();
        },

        async load() {
            this.loading = true;
            try {
                const pid = this.projectId || window._projectDetailId;
                if (!pid) return;
                const data = await api.get(`/projects/${pid}/figma`);
                this.files = data?.files || [];
                this.urls = data?.urls || [];
                if (this.files.length > 0) this.selectedFile = this.files[0];
            } catch {}
            finally { this.loading = false; }
        },

        async addUrl() {
            if (!this.newUrl.trim() || this.adding) return;
            this.adding = true;
            try {
                const pid = this.projectId || window._projectDetailId;
                await api.post(`/projects/${pid}/figma`, { url: this.newUrl.trim() });
                this.showAddModal = false;
                this.newUrl = '';
                await this.load();
                window.toast.success('Figma 파일이 연결되었습니다.');
            } catch (e) { window.toast.error(e.message || 'URL 등록 실패'); }
            finally { this.adding = false; }
        },

        async removeUrl(url) {
            if (!await window.confirmDialog('이 Figma 파일 연결을 해제하시겠습니까? 언제든 다시 연결할 수 있습니다.', { title: 'Figma 연결 해제', confirmText: '해제', danger: 'medium' })) return;
            try {
                const pid = this.projectId || window._projectDetailId;
                await api.del(`/projects/${pid}/figma`, { url });
                await this.load();
                window.toast.success('연결이 해제되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        selectFile(f) { this.selectedFile = f; },

        extractFileKey(url) {
            const m = url.match(/figma\.com\/(file|design)\/([a-zA-Z0-9]+)/);
            return m ? m[2] : null;
        },
    };
}

// ============ 3차 개발: 피드백 요청 대시보드 (S4-6, S4-7) ============

function feedbackRequestsPage() {
    return {
        requests: [],
        loading: true,
        filter: 'all',
        search: '',

        async init() {
            await this.load();
        },

        async load() {
            this.loading = true;
            try {
                const data = await api.get('/feedback/requests');
                this.requests = data?.requests || data || [];
            } catch { this.requests = []; }
            finally { this.loading = false; }
        },

        get filteredRequests() {
            let list = this.requests;
            if (this.filter !== 'all') list = list.filter(r => r.status === this.filter);
            if (this.search) {
                const q = this.search.toLowerCase();
                list = list.filter(r => (r.project_name || '').toLowerCase().includes(q) || (r.recipient_email || '').toLowerCase().includes(q));
            }
            return list;
        },

        get stats() {
            const s = { total: this.requests.length, pending: 0, viewed: 0, responded: 0, expired: 0, cancelled: 0 };
            this.requests.forEach(r => { if (s[r.status] !== undefined) s[r.status]++; });
            return s;
        },

        statusBadge(status) {
            return { pending: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400', viewed: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400', responded: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', expired: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400', cancelled: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400' }[status] || 'bg-gray-100 text-gray-600';
        },

        statusLabel(status) {
            return { pending: '대기 중', viewed: '열람', responded: '응답 완료', expired: '만료', cancelled: '취소' }[status] || status;
        },

        responseLabel(type) {
            return { approved: '승인', revision_requested: '수정 요청', comment: '의견' }[type] || type;
        },

        responseBadge(type) {
            return { approved: 'bg-green-100 text-green-700', revision_requested: 'bg-red-100 text-red-700', comment: 'bg-blue-100 text-blue-700' }[type] || 'bg-gray-100 text-gray-600';
        },

        async cancelRequest(id) {
            if (!await window.confirmDialog('이 피드백 요청을 취소하시겠습니까?', { title: '피드백 요청 취소', confirmText: '취소', danger: true })) return;
            try {
                await api.patch(`/feedback/requests/${id}/cancel`);
                await this.load();
                window.toast.success('피드백 요청이 취소되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        daysSince(dateStr) {
            if (!dateStr) return 0;
            return Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
        },
    };
}

// ============ 3차 개발: 고객 피드백 포털 (S4-3) ============

function feedbackPortalPage() {
    return {
        data: null,
        loading: true,
        error: null,
        submitted: false,
        expired: false,
        form: { response_type: '', content: '', client_name: '' },
        submitting: false,
        showConfirm: false,

        async init() {
            const m = (window.location.hash || '').match(/\/feedback-portal\/([a-zA-Z0-9_-]+)/);
            if (!m) { this.error = '유효하지 않은 링크입니다.'; this.loading = false; return; }
            try {
                this.data = await api.get(`/feedback/portal/${m[1]}`);
                if (this.data?.already_responded) this.submitted = true;
            } catch (e) {
                if (e.status === 410) { this.expired = true; this.error = '피드백 기한이 만료되었습니다.'; }
                else { this.error = e.message || '링크를 확인할 수 없습니다.'; }
            } finally { this.loading = false; }
        },

        selectType(type) { this.form.response_type = type; },

        async submit() {
            if (!this.form.response_type) { window.toast.warning('피드백 유형을 선택해주세요.'); return; }
            if (this.form.response_type !== 'approved' && !this.form.content.trim()) { window.toast.warning('내용을 입력해주세요.'); return; }
            this.showConfirm = true;
        },

        async confirmSubmit() {
            this.showConfirm = false;
            this.submitting = true;
            try {
                const m = (window.location.hash || '').match(/\/feedback-portal\/([a-zA-Z0-9_-]+)/);
                await api.post(`/feedback/portal/${m[1]}/response`, this.form);
                this.submitted = true;
                window.toast.success('피드백이 접수되었습니다.');
            } catch (e) { window.toast.error(e.message || '제출에 실패했습니다.'); }
            finally { this.submitting = false; }
        },
    };
}

// ============ 3차 개발: MCP 추천/관리 (S7-3, S7-4) ============

function mcpPage() {
    return {
        recommendations: [],
        catalog: [],
        patterns: null,
        loading: true,
        activeTab: 'recommendations',

        async init() {
            await Promise.all([this.loadRecommendations(), this.loadCatalog()]);
            this.loading = false;
        },

        async loadRecommendations() {
            try {
                const data = await api.get('/mcp/recommendations');
                this.recommendations = data?.recommendations || [];
            } catch { this.recommendations = []; }
        },

        async loadCatalog() {
            try {
                const data = await api.get('/mcp/catalog');
                this.catalog = data?.catalog || [];
            } catch { this.catalog = []; }
        },

        async loadPatterns() {
            try {
                this.patterns = await api.get('/mcp/patterns');
            } catch { this.patterns = null; }
        },

        async generateRecs() {
            try {
                await api.post('/mcp/recommendations/generate');
                await this.loadRecommendations();
                window.toast.success('추천이 갱신되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        async dismissRec(id) {
            try {
                await api.post(`/mcp/recommendations/${id}/dismiss`);
                this.recommendations = this.recommendations.filter(r => r.id !== id);
            } catch {}
        },

        mcpIcon(name) {
            const icons = { figma: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z', google_calendar: 'M19 4h-1V2h-2v2H8V2H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2z', github: 'M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.167 6.839 9.49.5.09.682-.217.682-.482 0-.237-.009-.866-.014-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.464-1.11-1.464-.908-.62.069-.607.069-.607 1.004.07 1.532 1.032 1.532 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.202 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.163 22 16.418 22 12c0-5.523-4.477-10-10-10z' };
            return icons[name] || icons.figma;
        },
    };
}

// ============ 4차 개발: Phase 1 — 게시판 (F-1~F-3) ============

function boardListPage() {
    return {
        boards: [], posts: [], loading: true,
        activeBoard: null, activeBoardType: 'notice',
        search: '', page: 1, totalPages: 1, size: 15,
        // 글 작성/수정
        showWriteModal: false, editingPost: null,
        writeForm: { title: '', content: '', file_urls: [] },
        _quill: null, saving: false,
        // 파일 업로드
        uploading: false,

        async init() {
            const teamId = window._selectedTeamId;
            await this.loadBoards(teamId);
            this.$el.addEventListener('route-changed', () => { if (this.$data.currentPage === 'boards') this.loadBoards(window._selectedTeamId); });
        },

        async loadBoards(teamId) {
            this.loading = true;
            try {
                const url = teamId ? `/teams/${teamId}/boards` : '/my/boards';
                this.boards = await api.get(url) || [];
                const target = this.boards.find(b => b.type === this.activeBoardType) || this.boards[0];
                if (target) { this.activeBoard = target; await this.loadPosts(); }
            } catch (e) { window.toast.error('게시판을 불러올 수 없습니다.'); }
            finally { this.loading = false; }
        },

        async switchBoard(board) {
            this.activeBoard = board;
            this.activeBoardType = board.type;
            this.page = 1; this.search = '';
            await this.loadPosts();
        },

        async loadPosts() {
            if (!this.activeBoard) return;
            try {
                const params = `page=${this.page}&size=${this.size}${this.search ? '&search=' + encodeURIComponent(this.search) : ''}`;
                const data = await api.get(`/boards/${this.activeBoard.id}/posts?${params}`);
                this.posts = data?.items || [];
                this.totalPages = Math.ceil((data?.total || 0) / this.size) || 1;
            } catch { this.posts = []; }
        },

        doSearch: debounce(function() { this.page = 1; this.loadPosts(); }, 400),

        openWrite(post = null) {
            this.editingPost = post;
            this.writeForm = post ? { title: post.title, content: post.content || '', file_urls: post.file_urls || [] } : { title: '', content: '', file_urls: [] };
            this.showWriteModal = true;
            this.$nextTick(() => this._initQuill());
        },

        _initQuill() {
            const el = this.$refs.boardQuillEditor;
            if (!el || this._quill) return;
            this._quill = new Quill(el, {
                theme: 'snow',
                placeholder: '내용을 입력하세요...',
                modules: { toolbar: [['bold', 'italic', 'underline'], [{ list: 'ordered' }, { list: 'bullet' }], ['link', 'image', 'clean']] },
            });
            if (this.writeForm.content) this._quill.root.innerHTML = this.writeForm.content;
            this._quill.on('text-change', () => { this.writeForm.content = this._quill.root.innerHTML; });
        },

        closeWrite() {
            this.showWriteModal = false;
            if (this._quill) { this._quill = null; }
        },

        async savePost() {
            if (!this.writeForm.title.trim()) { window.toast.warning('제목을 입력해주세요.'); return; }
            if (!this.writeForm.content.trim() || this.writeForm.content === '<p><br></p>') { window.toast.warning('내용을 입력해주세요.'); return; }
            this.saving = true;
            try {
                if (this.editingPost) {
                    await api.put(`/posts/${this.editingPost.id}`, this.writeForm);
                    window.toast.success('게시글이 수정되었습니다.');
                } else {
                    await api.post(`/boards/${this.activeBoard.id}/posts`, this.writeForm);
                    window.toast.success('게시글이 등록되었습니다.');
                }
                this.closeWrite();
                await this.loadPosts();
            } catch (e) { window.toast.error(e.message); }
            finally { this.saving = false; }
        },

        async deletePost(post) {
            if (!await window.confirmDialog('게시글을 삭제하시겠습니까?', { title: '게시글 삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/posts/${post.id}`);
                window.toast.success('삭제되었습니다.');
                await this.loadPosts();
            } catch (e) { window.toast.error(e.message); }
        },

        async togglePin(post) {
            try {
                const res = await api.patch(`/posts/${post.id}/pin`);
                post.is_pinned = res.is_pinned;
                window.toast.success(res.is_pinned ? '고정되었습니다.' : '고정 해제되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        async uploadFile(ev) {
            const file = ev.target.files[0];
            if (!file) return;
            this.uploading = true;
            try {
                const fd = new FormData();
                fd.append('file', file);
                const res = await api._fetch('/upload', { method: 'POST', body: fd, rawBody: true });
                if (res?.url) { this.writeForm.file_urls = [...(this.writeForm.file_urls || []), res.url]; }
                window.toast.success('파일이 첨부되었습니다.');
            } catch (e) { window.toast.error(e.message); }
            finally { this.uploading = false; ev.target.value = ''; }
        },

        removeFile(idx) { this.writeForm.file_urls.splice(idx, 1); },

        boardTypeLabel(t) { return { notice: '공지사항', free: '자유게시판', archive: '자료실' }[t] || t; },
        boardTypeIcon(t) { return { notice: '📢', free: '💬', archive: '📁' }[t] || '📋'; },
    };
}

function boardPostPage() {
    return {
        post: null, loading: true,
        commentText: '', commenting: false,

        async init() {
            const postId = this.$el.closest('[x-data]')?.__x?.$data?.pageParams?.postId || window.location.hash.match(/\/boards\/post\/(\d+)/)?.[1];
            if (!postId) { window.location.hash = '#/boards'; return; }
            await this.loadPost(postId);
        },

        async loadPost(postId) {
            this.loading = true;
            try { this.post = await api.get(`/posts/${postId}`); }
            catch { window.toast.error('게시글을 찾을 수 없습니다.'); window.location.hash = '#/boards'; }
            finally { this.loading = false; }
        },

        async addComment() {
            if (!this.commentText.trim()) return;
            this.commenting = true;
            try {
                const c = await api.post(`/posts/${this.post.id}/comments`, { content: this.commentText });
                this.post.comments = [...(this.post.comments || []), c];
                this.commentText = '';
            } catch (e) { window.toast.error(e.message); }
            finally { this.commenting = false; }
        },

        async deleteComment(commentId) {
            if (!await window.confirmDialog('댓글을 삭제하시겠습니까?', { title: '삭제', confirmText: '삭제', danger: true })) return;
            try {
                await api.del(`/comments/${commentId}`);
                this.post.comments = this.post.comments.filter(c => c.id !== commentId);
            } catch (e) { window.toast.error(e.message); }
        },

        goBack() { window.location.hash = '#/boards'; },
    };
}

// ============ 4차 개발: Phase 1 — 이메일 초대 (F-4) ============

function inviteManagement() {
    return {
        invites: [], loading: false,
        showInviteForm: false, inviteForm: { email: '', role: 'member' }, sending: false,

        async loadInvites(teamId) {
            if (!teamId) return;
            this.loading = true;
            try { this.invites = await api.get(`/teams/${teamId}/invites`) || []; }
            catch { this.invites = []; }
            finally { this.loading = false; }
        },

        async sendInvite(teamId) {
            if (!this.inviteForm.email.trim()) { window.toast.warning('이메일을 입력해주세요.'); return; }
            this.sending = true;
            try {
                await api.post(`/teams/${teamId}/invites`, this.inviteForm);
                window.toast.success('초대 이메일이 발송되었습니다.');
                this.inviteForm = { email: '', role: 'member' };
                this.showInviteForm = false;
                await this.loadInvites(teamId);
            } catch (e) { window.toast.error(e.message); }
            finally { this.sending = false; }
        },

        async cancelInvite(inviteId, teamId) {
            if (!await window.confirmDialog('초대를 취소하시겠습니까?', { title: '초대 취소', confirmText: '취소', danger: true })) return;
            try {
                await api.del(`/invites/${inviteId}`);
                await this.loadInvites(teamId);
                window.toast.success('초대가 취소되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        statusLabel(s) { return { pending: '대기 중', accepted: '수락됨', expired: '만료' }[s] || s; },
        statusColor(s) { return { pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400', accepted: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400', expired: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400' }[s] || ''; },
    };
}

// ============ 4차 개발: Phase 1 — 초대 수락 페이지 (F-5) ============

function inviteAcceptPage() {
    return {
        invite: null, loading: true, accepting: false, error: '',

        async init() {
            const token = window.location.hash.match(/\/invite\/([a-zA-Z0-9_-]+)/)?.[1];
            if (!token) { this.error = '잘못된 초대 링크입니다.'; this.loading = false; return; }
            try {
                this.invite = await api.get(`/invites/accept/${token}`);
                if (this.invite?.expired) this.error = '만료된 초대입니다.';
            } catch { this.error = '초대를 찾을 수 없습니다.'; }
            finally { this.loading = false; }
        },

        async accept() {
            const token = window.location.hash.match(/\/invite\/([a-zA-Z0-9_-]+)/)?.[1];
            this.accepting = true;
            try {
                const res = await api.post(`/invites/accept/${token}`);
                window.toast.success(`'${res.team_name || ''}' 팀에 합류했습니다!`);
                window.location.hash = '#/dashboard';
            } catch (e) { window.toast.error(e.message); }
            finally { this.accepting = false; }
        },
    };
}

// ============ 4차 개발: Phase 2 — 대시보드 캘린더 위젯 (F-7) ============

function calendarWidget() {
    return {
        year: new Date().getFullYear(), month: new Date().getMonth(),
        tasks: [], selectedDate: null, selectedTasks: [],

        async init() {
            await this.loadTasks();
        },

        async loadTasks() {
            try {
                const m = String(this.month + 1).padStart(2, '0');
                const data = await api.get(`/tasks?page=1&size=200`);
                this.tasks = (data?.items || []).filter(t => t.due_date);
            } catch { this.tasks = []; }
        },

        get daysInMonth() {
            return new Date(this.year, this.month + 1, 0).getDate();
        },

        get firstDayOfWeek() {
            return new Date(this.year, this.month, 1).getDay();
        },

        get calendarDays() {
            const days = [];
            for (let i = 0; i < this.firstDayOfWeek; i++) days.push(null);
            for (let d = 1; d <= this.daysInMonth; d++) days.push(d);
            return days;
        },

        get monthLabel() {
            return `${this.year}년 ${this.month + 1}월`;
        },

        prevMonth() {
            if (this.month === 0) { this.year--; this.month = 11; } else { this.month--; }
            this.selectedDate = null; this.loadTasks();
        },

        nextMonth() {
            if (this.month === 11) { this.year++; this.month = 0; } else { this.month++; }
            this.selectedDate = null; this.loadTasks();
        },

        dateStr(d) {
            return `${this.year}-${String(this.month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        },

        tasksForDay(d) {
            if (!d) return [];
            const ds = this.dateStr(d);
            return this.tasks.filter(t => t.due_date === ds);
        },

        selectDay(d) {
            if (!d) return;
            this.selectedDate = d;
            this.selectedTasks = this.tasksForDay(d);
        },

        isToday(d) {
            if (!d) return false;
            const today = new Date();
            return d === today.getDate() && this.month === today.getMonth() && this.year === today.getFullYear();
        },
    };
}

// ============ 4차 개발: Phase 2 — 내 업무 멀티팀 (F-8) ============

function myTasksPage() {
    return {
        tasks: [], teams: [], loading: true,
        filterTeam: null, filterStatus: '',

        async init() {
            await this.load();
            this.$el.addEventListener('route-changed', () => { if (this.$data.currentPage === 'myTasks') this.load(); });
        },

        async load() {
            this.loading = true;
            try {
                let url = '/my/tasks';
                const params = [];
                if (this.filterTeam) params.push(`team_id=${this.filterTeam}`);
                if (this.filterStatus) params.push(`status=${encodeURIComponent(this.filterStatus)}`);
                if (params.length) url += '?' + params.join('&');
                const data = await api.get(url);
                this.tasks = data?.items || [];
                this.teams = data?.teams || [];
            } catch (e) { window.toast.error(e.message); }
            finally { this.loading = false; }
        },

        async savePriority() {
            const taskIds = this.tasks.map(t => t.id);
            try {
                await api.put('/my/tasks/priority', { task_ids: taskIds });
                window.toast.success('우선순위가 저장되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        moveUp(idx) {
            if (idx <= 0) return;
            [this.tasks[idx - 1], this.tasks[idx]] = [this.tasks[idx], this.tasks[idx - 1]];
            this.tasks = [...this.tasks];
            this.savePriority();
        },

        moveDown(idx) {
            if (idx >= this.tasks.length - 1) return;
            [this.tasks[idx], this.tasks[idx + 1]] = [this.tasks[idx + 1], this.tasks[idx]];
            this.tasks = [...this.tasks];
            this.savePriority();
        },

        teamColor(teamId) {
            const colors = ['bg-blue-100 text-blue-700', 'bg-green-100 text-green-700', 'bg-purple-100 text-purple-700', 'bg-orange-100 text-orange-700', 'bg-pink-100 text-pink-700'];
            const idx = this.teams.findIndex(t => t.id === teamId);
            return colors[idx % colors.length] || colors[0];
        },
    };
}

// ============ 4차 개발: Phase 2 — 랜딩 페이지 (F-9) ============

function landingPage() {
    return {
        features: [
            { icon: 'M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z', title: 'AI 어시스턴트', desc: '업무 현황, 마감일, 팀 워크로드를 자연어로 질의. 내장 챗봇이 실시간 답변합니다.', color: 'indigo' },
            { icon: 'M5.5 3.21V20.8c0 .45.54.67.85.35l4.86-4.86a.5.5 0 01.35-.15h6.87a.5.5 0 00.35-.85L6.35 2.85a.5.5 0 00-.85.36z', title: 'Figma 연동', desc: '시안 자동 미리보기, 변경 알림. 고객에게 포털 링크로 시안 공유 + 피드백 수집.', color: 'purple', filled: true },
            { icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z', title: '고객 피드백', desc: '이메일로 피드백 요청 → 비로그인 포털에서 승인/수정요청. 자동 리마인더 발송.', color: 'green' },
            { icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z', title: '수금 관리', desc: '계약금/중도금/잔금 일정 관리. D-7 예정 알림, 연체 자동 알림.', color: 'amber' },
            { icon: 'M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z', title: 'AI 보고서', desc: '일간/주간/월간 보고서 자동 생성. Gemini AI가 프로젝트 현황을 분석합니다.', color: 'blue' },
            { icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z', title: '팀 협업', desc: '실시간 알림, @멘션, 댓글 스레드, 게시판. 멤버 간 채팅으로 외부 메신저 불필요.', color: 'rose' },
        ],
        colorMap: {
            indigo: { bg: 'bg-indigo-100 dark:bg-indigo-900/30', text: 'text-indigo-600 dark:text-indigo-400' },
            purple: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-600 dark:text-purple-400' },
            green:  { bg: 'bg-green-100 dark:bg-green-900/30',  text: 'text-green-600 dark:text-green-400' },
            amber:  { bg: 'bg-amber-100 dark:bg-amber-900/30',  text: 'text-amber-600 dark:text-amber-400' },
            blue:   { bg: 'bg-blue-100 dark:bg-blue-900/30',   text: 'text-blue-600 dark:text-blue-400' },
            rose:   { bg: 'bg-rose-100 dark:bg-rose-900/30',   text: 'text-rose-600 dark:text-rose-400' },
        },
        goLogin() { window.dispatchEvent(new CustomEvent('open-login')); },
    };
}

// ============ 4차 개발: Phase 3 — 멤버 간 채팅 (F-10) ============

function chatPage() {
    return {
        rooms: [], messages: [], loading: true,
        selectedRoom: null, msgInput: '', sending: false,
        showCreateModal: false, createForm: { type: 'direct', member_ids: [], name: '' },
        teamMembers: [], searchMember: '',
        _sseSource: null, _scrollLock: false,

        async init() {
            await this.loadRooms();
            this._connectSSE();
            const roomId = window.location.hash.match(/\/chat\/(\d+)/)?.[1];
            if (roomId) {
                const room = this.rooms.find(r => r.id === parseInt(roomId));
                if (room) await this.selectRoom(room);
            }
            this.$el.addEventListener('route-changed', () => {
                if (this.$data?.currentPage !== 'chat') { this._disconnectSSE(); }
            });
        },

        async loadRooms() {
            this.loading = true;
            try { this.rooms = await api.get('/chat/rooms') || []; }
            catch { this.rooms = []; }
            finally { this.loading = false; }
        },

        async selectRoom(room) {
            this.selectedRoom = room;
            await this.loadMessages(room.id);
            await api.patch(`/chat/rooms/${room.id}/read`);
            room.unread_count = 0;
            this._scrollToBottom();
        },

        async loadMessages(roomId) {
            try {
                const data = await api.get(`/chat/rooms/${roomId}/messages?page=1&size=50`);
                this.messages = data?.items || [];
            } catch { this.messages = []; }
        },

        async sendMessage() {
            if (!this.msgInput.trim() || !this.selectedRoom) return;
            this.sending = true;
            try {
                const msg = await api.post(`/chat/rooms/${this.selectedRoom.id}/messages`, { content: this.msgInput });
                this.messages.push(msg);
                this.msgInput = '';
                this._scrollToBottom();
            } catch (e) { window.toast.error(e.message); }
            finally { this.sending = false; }
        },

        _connectSSE() {
            try {
                const es = new EventSource('/api/v1/chat/stream');
                es.onmessage = (ev) => {
                    try {
                        const data = JSON.parse(ev.data);
                        if (data.type === 'new_message') {
                            if (this.selectedRoom?.id === data.room_id) {
                                this.messages.push(data.message);
                                this._scrollToBottom();
                            }
                            const room = this.rooms.find(r => r.id === data.room_id);
                            if (room) {
                                room.last_message = data.message;
                                if (this.selectedRoom?.id !== data.room_id) room.unread_count = (room.unread_count || 0) + 1;
                            }
                        }
                    } catch {}
                };
                es.onerror = () => { es.close(); setTimeout(() => this._connectSSE(), 5000); };
                this._sseSource = es;
            } catch {}
        },

        _disconnectSSE() {
            if (this._sseSource) {
                this._sseSource.close();
                this._sseSource = null;
            }
        },

        _scrollToBottom() {
            this.$nextTick(() => {
                const el = this.$refs.chatMessages;
                if (el) el.scrollTop = el.scrollHeight;
            });
        },

        async openCreate() {
            this.showCreateModal = true;
            this.createForm = { type: 'direct', member_ids: [], name: '' };
            await this.loadTeamMembers();
        },

        async loadTeamMembers() {
            const teamId = window._selectedTeamId;
            if (!teamId) return;
            try {
                const data = await api.get(`/teams/${teamId}`);
                this.teamMembers = data?.members || [];
            } catch { this.teamMembers = []; }
        },

        toggleMember(userId) {
            const idx = this.createForm.member_ids.indexOf(userId);
            if (idx >= 0) this.createForm.member_ids.splice(idx, 1);
            else this.createForm.member_ids.push(userId);
        },

        async createRoom() {
            if (this.createForm.member_ids.length === 0) { window.toast.warning('멤버를 선택해주세요.'); return; }
            try {
                const res = await api.post('/chat/rooms', this.createForm);
                this.showCreateModal = false;
                await this.loadRooms();
                const room = this.rooms.find(r => r.id === res.id);
                if (room) await this.selectRoom(room);
            } catch (e) { window.toast.error(e.message); }
        },

        get filteredMembers() {
            if (!this.searchMember) return this.teamMembers;
            const q = this.searchMember.toLowerCase();
            return this.teamMembers.filter(m => (m.name || m.email || '').toLowerCase().includes(q));
        },

        isMine(msg) { return msg.sender_name === null; },

        formatTime(iso) {
            if (!iso) return '';
            const d = new Date(iso);
            return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
        },
    };
}

// ============ 4차 개발: Phase 4 — 출퇴근 기록 + 위젯 (F-11) ============

function attendancePage() {
    return {
        today: null, loading: true,
        month: new Date().toISOString().slice(0, 7),
        records: [], stats: null,
        // F-7: 퇴근 업무 보고
        showWorkReport: false, workReportText: '', workReportSubmitting: false,

        async init() {
            await Promise.all([this.loadToday(), this.loadMonth()]);
            this.loading = false;
            this.$el.addEventListener('route-changed', () => {
                if (this.$data.currentPage === 'attendance') { this.loadToday(); this.loadMonth(); }
            });
        },

        async loadToday() {
            try { this.today = await api.get('/attendance/today'); } catch { this.today = null; }
        },

        async loadMonth() {
            try {
                const data = await api.get(`/attendance/my?month=${this.month}`);
                this.records = data?.records || [];
                this.stats = data?.stats || null;
            } catch { this.records = []; this.stats = null; }
        },

        async checkIn() {
            try {
                this.today = await api.post('/attendance/check-in');
                window.toast.success('출근이 기록되었습니다.');
            } catch (e) { window.toast.error(e.message); }
        },

        async checkOut() {
            try {
                this.today = await api.post('/attendance/check-out');
                window.toast.success('퇴근이 기록되었습니다.');
                await this.loadMonth();
                // F-7: 퇴근 후 업무 보고 모달 표시
                this.showWorkReport = true;
            } catch (e) { window.toast.error(e.message); }
        },

        async submitWorkReport() {
            if (!this.workReportText.trim()) { this.showWorkReport = false; return; }
            this.workReportSubmitting = true;
            try {
                // 업무 보고를 활동 로그로 기록
                await api.post('/activity', { type: 'work_report', content: this.workReportText.trim() });
                window.toast.success('업무 보고가 저장되었습니다.');
            } catch { /* 실패해도 퇴근은 완료됨 */ }
            finally { this.showWorkReport = false; this.workReportText = ''; this.workReportSubmitting = false; }
        },

        changeMonth(dir) {
            const [y, m] = this.month.split('-').map(Number);
            const d = new Date(y, m - 1 + dir, 1);
            this.month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
            this.loadMonth();
        },

        statusLabel(s) { return { normal: '정상', late: '지각', early_leave: '조퇴', absent: '결근' }[s] || s || '미출근'; },
        statusColor(s) { return { normal: 'text-green-600', late: 'text-orange-600', early_leave: 'text-yellow-600', absent: 'text-red-600' }[s] || 'text-gray-400'; },
        statusBadge(s) { return { normal: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', late: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400', early_leave: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400', absent: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' }[s] || 'bg-gray-100 text-gray-500'; },
    };
}

// ============ 4차 개발: Phase 4 — 팀 근태 관리 (F-12) ============

function teamAttendancePage() {
    return {
        teamData: null, loading: true,
        month: new Date().toISOString().slice(0, 7),

        async init() {
            await this.load();
        },

        async load() {
            const teamId = window._selectedTeamId;
            if (!teamId) { window.toast.warning('팀을 먼저 선택해주세요.'); this.loading = false; return; }
            this.loading = true;
            try { this.teamData = await api.get(`/teams/${teamId}/attendance?month=${this.month}`); }
            catch (e) { window.toast.error(e.message); this.teamData = null; }
            finally { this.loading = false; }
        },

        changeMonth(dir) {
            const [y, m] = this.month.split('-').map(Number);
            const d = new Date(y, m - 1 + dir, 1);
            this.month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
            this.load();
        },

        statusLabel(s) { return { normal: '정상', late: '지각', early_leave: '조퇴', absent: '결근' }[s] || s; },
        statusBadge(s) { return { normal: 'bg-green-100 text-green-700', late: 'bg-orange-100 text-orange-700', early_leave: 'bg-yellow-100 text-yellow-700', absent: 'bg-red-100 text-red-700' }[s] || 'bg-gray-100 text-gray-500'; },
    };
}

// ============ 4차 개발: Phase 4 — 근무 정책 (F-13, teamSettings 내 탭) ============

function attendancePolicyWidget() {
    return {
        policy: null, loading: false, saving: false,
        form: { default_check_in: '09:00', default_check_out: '18:00', work_hours: 8, break_hours: 1 },

        async loadPolicy(teamId) {
            if (!teamId) return;
            this.loading = true;
            try {
                this.policy = await api.get(`/teams/${teamId}/attendance/policy`);
                this.form = {
                    default_check_in: this.policy.default_check_in || '09:00',
                    default_check_out: this.policy.default_check_out || '18:00',
                    work_hours: this.policy.work_hours || 8,
                    break_hours: this.policy.break_hours || 1,
                };
            } catch { this.policy = null; }
            finally { this.loading = false; }
        },

        async savePolicy(teamId) {
            this.saving = true;
            try {
                await api.put(`/teams/${teamId}/attendance/policy`, this.form);
                window.toast.success('근무 정책이 저장되었습니다.');
            } catch (e) { window.toast.error(e.message); }
            finally { this.saving = false; }
        },
    };
}

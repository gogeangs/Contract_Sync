// Toast 알림 시스템
function toastManager() {
    return {
        toasts: [],
        _id: 0,

        show(message, type = 'info', duration = 3000) {
            const id = ++this._id;
            this.toasts.push({ id, message, type, visible: true });
            setTimeout(() => this.dismiss(id), duration);
        },

        success(message) { this.show(message, 'success', 3000); },
        error(message) { this.show(message, 'error', 5000); },
        warning(message) { this.show(message, 'warning', 4000); },
        info(message) { this.show(message, 'info', 3000); },

        dismiss(id) {
            const t = this.toasts.find(t => t.id === id);
            if (t) t.visible = false;
            setTimeout(() => {
                this.toasts = this.toasts.filter(t => t.id !== id);
            }, 300);
        }
    };
}

// 전역 toast 함수 (Alpine 외부에서도 호출 가능)
window._toast = { _queue: [], ready: false };
window.toast = {
    success(msg) { window._toast.ready ? window.dispatchEvent(new CustomEvent('toast', { detail: { message: msg, type: 'success' } })) : window._toast._queue.push({ message: msg, type: 'success' }); },
    error(msg) { window._toast.ready ? window.dispatchEvent(new CustomEvent('toast', { detail: { message: msg, type: 'error' } })) : window._toast._queue.push({ message: msg, type: 'error' }); },
    warning(msg) { window._toast.ready ? window.dispatchEvent(new CustomEvent('toast', { detail: { message: msg, type: 'warning' } })) : window._toast._queue.push({ message: msg, type: 'warning' }); },
    info(msg) { window._toast.ready ? window.dispatchEvent(new CustomEvent('toast', { detail: { message: msg, type: 'info' } })) : window._toast._queue.push({ message: msg, type: 'info' }); },
};

function authState() {
    return {
        user: null,
        teams: [],
        loading: true,
        showModal: false,
        modalMode: 'login', // 'login', 'signup', 'verify'

        // 폼 데이터
        email: '',
        password: '',
        passwordConfirm: '',
        verificationCode: '',

        // 상태
        formLoading: false,
        formError: '',
        formSuccess: '',
        emailVerified: false,

        // 다크 모드
        darkMode: false,

        async init() {
            this.initDarkMode();
            await this.checkAuth();
        },

        initDarkMode() {
            const saved = localStorage.getItem('darkMode');
            if (saved !== null) {
                this.darkMode = saved === 'true';
            } else {
                this.darkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
            }
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

        async checkAuth() {
            try {
                const response = await fetch('/api/v1/auth/me');
                const data = await response.json();

                if (data.logged_in && data.user) {
                    this.user = data.user;
                    this.teams = data.teams || [];
                    this.loadUnreadCount();
                    // 30초마다 알림 카운트 갱신
                    if (!this._notifInterval) {
                        this._notifInterval = setInterval(() => this.loadUnreadCount(), 30000);
                    }
                    window.dispatchEvent(new CustomEvent('user-logged-in'));
                } else {
                    window.dispatchEvent(new CustomEvent('user-not-logged-in'));
                }
            } catch (err) {
                console.error('인증 확인 실패:', err);
                window.dispatchEvent(new CustomEvent('user-not-logged-in'));
            } finally {
                this.loading = false;
            }
        },

        openLogin() {
            this.resetForm();
            this.modalMode = 'login';
            this.showModal = true;
        },

        openSignup() {
            this.resetForm();
            this.modalMode = 'signup';
            this.showModal = true;
        },

        closeModal() {
            this.showModal = false;
            this.resetForm();
        },

        resetForm() {
            this.email = '';
            this.password = '';
            this.passwordConfirm = '';
            this.verificationCode = '';
            this.formError = '';
            this.formSuccess = '';
            this.emailVerified = false;
        },

        async sendVerificationCode() {
            if (!this.email) {
                this.formError = '이메일을 입력해주세요.';
                return;
            }

            this.formLoading = true;
            this.formError = '';

            try {
                const response = await fetch('/api/v1/auth/send-code', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: this.email })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || '인증코드 발송 실패');
                }

                // 개발 모드: 인증코드가 응답에 포함된 경우 자동 입력
                if (data.dev_code) {
                    this.verificationCode = data.dev_code;
                    this.formSuccess = data.message;
                } else {
                    this.formSuccess = '인증코드가 발송되었습니다. 이메일을 확인해주세요.';
                }
                this.modalMode = 'verify';
            } catch (err) {
                this.formError = err.message;
            } finally {
                this.formLoading = false;
            }
        },

        async verifyCode() {
            if (!this.verificationCode) {
                this.formError = '인증코드를 입력해주세요.';
                return;
            }

            this.formLoading = true;
            this.formError = '';

            try {
                const response = await fetch('/api/v1/auth/verify-code', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: this.email,
                        code: this.verificationCode
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || '인증 실패');
                }

                this.emailVerified = true;
                this.formSuccess = '이메일 인증 완료! 비밀번호를 설정해주세요.';
                this.modalMode = 'signup';
            } catch (err) {
                this.formError = err.message;
            } finally {
                this.formLoading = false;
            }
        },

        async signup() {
            if (!this.emailVerified) {
                this.formError = '이메일 인증이 필요합니다.';
                return;
            }

            if (!this.password || !this.passwordConfirm) {
                this.formError = '비밀번호를 입력해주세요.';
                return;
            }

            if (this.password !== this.passwordConfirm) {
                this.formError = '비밀번호가 일치하지 않습니다.';
                return;
            }

            if (this.password.length < 6) {
                this.formError = '비밀번호는 6자 이상이어야 합니다.';
                return;
            }

            this.formLoading = true;
            this.formError = '';

            try {
                const response = await fetch('/api/v1/auth/signup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: this.email,
                        password: this.password,
                        password_confirm: this.passwordConfirm
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || '회원가입 실패');
                }

                this.closeModal();
                window.location.reload();
            } catch (err) {
                this.formError = err.message;
            } finally {
                this.formLoading = false;
            }
        },

        async login() {
            if (!this.email || !this.password) {
                this.formError = '이메일과 비밀번호를 입력해주세요.';
                return;
            }

            this.formLoading = true;
            this.formError = '';

            try {
                const response = await fetch('/api/v1/auth/login/email', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: this.email,
                        password: this.password
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || '로그인 실패');
                }

                this.closeModal();
                window.location.reload();
            } catch (err) {
                this.formError = err.message;
            } finally {
                this.formLoading = false;
            }
        },

        // 알림 상태
        notifications: [],
        unreadCount: 0,
        showNotifPanel: false,
        notifLoading: false,

        async loadUnreadCount() {
            try {
                const res = await fetch('/api/v1/notifications/unread-count');
                if (res.ok) {
                    const data = await res.json();
                    this.unreadCount = data.unread_count;
                }
            } catch (err) { /* ignore */ }
        },

        async loadNotifications() {
            this.notifLoading = true;
            try {
                const res = await fetch('/api/v1/notifications?size=20');
                if (res.ok) {
                    const data = await res.json();
                    this.notifications = data.items || [];
                    this.unreadCount = data.unread_count;
                }
            } catch (err) { console.error('알림 로드 실패:', err); }
            finally { this.notifLoading = false; }
        },

        toggleNotifications() {
            this.showNotifPanel = !this.showNotifPanel;
            if (this.showNotifPanel) this.loadNotifications();
        },

        async markNotifRead(id) {
            await fetch(`/api/v1/notifications/${id}/read`, { method: 'PATCH' });
            const n = this.notifications.find(x => x.id === id);
            if (n) n.is_read = true;
            this.unreadCount = Math.max(0, this.unreadCount - 1);
        },

        async markAllNotifRead() {
            await fetch('/api/v1/notifications/read-all', { method: 'PATCH' });
            this.notifications.forEach(n => n.is_read = true);
            this.unreadCount = 0;
        },

        getNotifTimeAgo(isoStr) {
            if (!isoStr) return '';
            const diff = Date.now() - new Date(isoStr).getTime();
            const mins = Math.floor(diff / 60000);
            if (mins < 1) return '방금';
            if (mins < 60) return `${mins}분 전`;
            const hours = Math.floor(mins / 60);
            if (hours < 24) return `${hours}시간 전`;
            return `${Math.floor(hours / 24)}일 전`;
        },

        async logout() {
            try {
                await fetch('/api/v1/auth/logout', { method: 'POST' });
                this.user = null;
                window.location.reload();
            } catch (err) {
                console.error('로그아웃 실패:', err);
            }
        }
    };
}

function scheduleExtractor() {
    return {
        file: null,
        loading: false,
        result: null,
        error: null,
        dragover: false,
        editMode: false,
        saveLoading: false,
        infoTab: 'basic', // 'basic', 'period', 'payment'
        showMyPage: false,
        myContracts: [],
        myContractsLoading: false,
        contractFilterYear: '',
        contractFilterMonth: '',

        // 로그인 상태
        isLoggedIn: false,

        // 대시보드 상태
        showDashboard: false,
        dashboard: null,
        dashboardLoading: false,
        taskFilter: 'all', // all, pending, in_progress, completed
        taskSearch: '',

        // 팀 상태
        selectedTeamId: null, // null = 개인, 숫자 = 팀
        teamMembers: [],
        showTeamManage: false,
        teamManageLoading: false,
        teamDetail: null,
        inviteEmail: '',
        inviteLoading: false,

        // 업무 추가 폼
        showAddTask: false,
        newTask: {
            contract_id: null,
            task_name: '',
            phase: '',
            due_date: '',
            priority: '보통',
            status: '대기',
            assignee_id: '',
        },
        addTaskLoading: false,

        init() {
            // 이벤트 리스너는 HTML에서 처리
        },

        async loadDashboard() {
            this.dashboardLoading = true;
            try {
                const params = this.selectedTeamId ? `?team_id=${this.selectedTeamId}` : '';
                const response = await fetch(`/api/v1/contracts/dashboard/summary${params}`);
                if (response.ok) {
                    this.dashboard = await response.json();
                } else if (response.status === 401) {
                    this.dashboard = null;
                }
            } catch (err) {
                console.error('대시보드 로드 실패:', err);
            } finally {
                this.dashboardLoading = false;
            }
        },

        async switchTeam(teamId) {
            this.selectedTeamId = teamId || null;
            if (this.selectedTeamId) {
                await this.loadTeamMembers(this.selectedTeamId);
                await this.loadPermissions(this.selectedTeamId);
            } else {
                this.teamMembers = [];
                this.teamPermissions = [];
            }
            if (this.showDashboard) {
                await this.loadDashboard();
            }
        },

        async loadTeamMembers(teamId) {
            try {
                const response = await fetch(`/api/v1/teams/${teamId}`);
                if (response.ok) {
                    const data = await response.json();
                    this.teamMembers = data.members || [];
                    this.teamDetail = data;
                }
            } catch (err) {
                console.error('팀 멤버 로드 실패:', err);
            }
        },

        async createTeam(name, description) {
            try {
                const response = await fetch('/api/v1/teams', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, description })
                });
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || '팀 생성 실패');
                }
                window.toast.success('팀이 생성되었습니다.');
                // authState의 teams 갱신
                window.dispatchEvent(new CustomEvent('refresh-auth'));
                return await response.json();
            } catch (err) {
                window.toast.error(err.message);
                return null;
            }
        },

        async inviteMember(teamId, email) {
            this.inviteLoading = true;
            try {
                const response = await fetch(`/api/v1/teams/${teamId}/members`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                });
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || '초대 실패');
                }
                window.toast.success('멤버가 추가되었습니다.');
                await this.loadTeamMembers(teamId);
                this.inviteEmail = '';
            } catch (err) {
                window.toast.error(err.message);
            } finally {
                this.inviteLoading = false;
            }
        },

        async removeMember(teamId, userId) {
            if (!confirm('이 멤버를 제거하시겠습니까?')) return;
            try {
                const response = await fetch(`/api/v1/teams/${teamId}/members/${userId}`, {
                    method: 'DELETE'
                });
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || '멤버 제거 실패');
                }
                window.toast.success('멤버가 제거되었습니다.');
                await this.loadTeamMembers(teamId);
            } catch (err) {
                window.toast.error(err.message);
            }
        },

        async updateMemberRole(teamId, userId, role) {
            try {
                const response = await fetch(`/api/v1/teams/${teamId}/members/${userId}/role`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ role })
                });
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || '역할 변경 실패');
                }
                window.toast.success('역할이 변경되었습니다.');
                await this.loadTeamMembers(teamId);
            } catch (err) {
                window.toast.error(err.message);
            }
        },

        async deleteTeam(teamId) {
            if (!confirm('이 팀을 삭제하시겠습니까? 팀 계약은 유지됩니다.')) return;
            try {
                const response = await fetch(`/api/v1/teams/${teamId}`, { method: 'DELETE' });
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || '팀 삭제 실패');
                }
                window.toast.success('팀이 삭제되었습니다.');
                this.selectedTeamId = null;
                this.teamMembers = [];
                this.showTeamManage = false;
                window.dispatchEvent(new CustomEvent('refresh-auth'));
            } catch (err) {
                window.toast.error(err.message);
            }
        },

        async updateTaskAssignee(contractId, taskId, assigneeId) {
            try {
                const response = await fetch(`/api/v1/contracts/${contractId}/tasks/assignee`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ task_id: String(taskId), assignee_id: assigneeId || null })
                });

                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || '담당자 변경 실패');
                }

                const data = await response.json();

                // 로컬 데이터 업데이트
                if (this.dashboard?.tasks) {
                    const task = this.dashboard.tasks.find(
                        t => t.contract_id === contractId && t.task_id === taskId
                    );
                    if (task) {
                        task.assignee_id = data.assignee_id;
                        task.assignee_name = data.assignee_name;
                    }
                }
            } catch (err) {
                window.toast.error(err.message);
            }
        },

        get filteredTasks() {
            if (!this.dashboard?.tasks) return [];
            let tasks = this.dashboard.tasks;

            // 상태 필터
            if (this.taskFilter !== 'all') {
                const statusMap = {
                    'pending': '대기',
                    'in_progress': '진행중',
                    'completed': '완료'
                };
                tasks = tasks.filter(t => t.status === statusMap[this.taskFilter]);
            }

            // 검색 필터
            if (this.taskSearch.trim()) {
                const q = this.taskSearch.trim().toLowerCase();
                tasks = tasks.filter(t =>
                    (t.task_name || '').toLowerCase().includes(q) ||
                    (t.contract_name || '').toLowerCase().includes(q) ||
                    (t.phase || '').toLowerCase().includes(q)
                );
            }

            return tasks;
        },

        // D-day 계산 헬퍼
        getDaysUntil(dateStr) {
            if (!dateStr) return null;
            const due = new Date(dateStr + 'T00:00:00');
            if (isNaN(due.getTime())) return null;
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            return Math.ceil((due - today) / (1000 * 60 * 60 * 24));
        },

        getDdayLabel(dateStr) {
            const days = this.getDaysUntil(dateStr);
            if (days === null) return '';
            if (days < 0) return `D+${Math.abs(days)}`;
            if (days === 0) return 'D-Day';
            return `D-${days}`;
        },

        getDdayClass(dateStr) {
            const days = this.getDaysUntil(dateStr);
            if (days === null) return '';
            if (days < 0) return 'bg-red-600 text-white';
            if (days === 0) return 'bg-red-500 text-white';
            if (days <= 3) return 'bg-red-100 text-red-700';
            if (days <= 7) return 'bg-orange-100 text-orange-700';
            return 'bg-gray-100 text-gray-600';
        },

        getTaskBorderClass(task) {
            if (task.status === '완료') return 'border-gray-200';
            const days = this.getDaysUntil(task.due_date);
            if (days === null) return 'border-gray-200';
            if (days < 0) return 'border-red-400 border-l-4';
            if (days <= 3) return 'border-red-300 border-l-4';
            if (days <= 7) return 'border-orange-300 border-l-4';
            return 'border-gray-200';
        },

        // 업무 진행률
        get taskProgressPercent() {
            const total = this.dashboard?.total_tasks || 0;
            if (total === 0) return { pending: 0, inProgress: 0, completed: 0 };
            return {
                pending: Math.round((this.dashboard.pending_tasks / total) * 100),
                inProgress: Math.round((this.dashboard.in_progress_tasks / total) * 100),
                completed: Math.round((this.dashboard.completed_tasks / total) * 100),
            };
        },

        // 드래그 정렬
        _dragIdx: null,

        get canDragTasks() {
            return this.taskFilter === 'all' && !this.taskSearch.trim();
        },

        handleTaskDragStart(idx) {
            this._dragIdx = idx;
        },

        handleTaskDragOver(_, idx) {
            if (this._dragIdx === null || this._dragIdx === idx) return;
            const tasks = this.dashboard.tasks;
            const dragged = tasks.splice(this._dragIdx, 1)[0];
            tasks.splice(idx, 0, dragged);
            this._dragIdx = idx;
        },

        handleTaskDragEnd() {
            this._dragIdx = null;
        },

        // 계약별 색상 구분
        _contractColors: {},
        _colorPalette: [
            { bg: 'bg-violet-100', text: 'text-violet-700', dot: 'bg-violet-500' },
            { bg: 'bg-sky-100', text: 'text-sky-700', dot: 'bg-sky-500' },
            { bg: 'bg-emerald-100', text: 'text-emerald-700', dot: 'bg-emerald-500' },
            { bg: 'bg-amber-100', text: 'text-amber-700', dot: 'bg-amber-500' },
            { bg: 'bg-rose-100', text: 'text-rose-700', dot: 'bg-rose-500' },
            { bg: 'bg-cyan-100', text: 'text-cyan-700', dot: 'bg-cyan-500' },
            { bg: 'bg-fuchsia-100', text: 'text-fuchsia-700', dot: 'bg-fuchsia-500' },
            { bg: 'bg-lime-100', text: 'text-lime-700', dot: 'bg-lime-500' },
            { bg: 'bg-orange-100', text: 'text-orange-700', dot: 'bg-orange-500' },
            { bg: 'bg-teal-100', text: 'text-teal-700', dot: 'bg-teal-500' },
        ],

        getContractColor(contractName) {
            if (!contractName) return this._colorPalette[0];
            if (this._contractColors[contractName]) return this._contractColors[contractName];

            // 문자열 해시로 일관된 색상 매핑
            let hash = 0;
            for (let i = 0; i < contractName.length; i++) {
                hash = contractName.charCodeAt(i) + ((hash << 5) - hash);
            }
            const idx = Math.abs(hash) % this._colorPalette.length;
            this._contractColors[contractName] = this._colorPalette[idx];
            return this._colorPalette[idx];
        },

        _dispatchPage(page) {
            window.dispatchEvent(new CustomEvent('active-page', { detail: page }));
        },

        goToUpload() {
            this.showDashboard = false;
            this.showMyPage = false;
            this.result = null;
            this.file = null;
            this.error = null;
            this.editMode = false;
            this._dispatchPage('upload');
        },

        handleFileSelect(event) {
            const file = event.target.files[0];
            if (file) {
                this.validateAndSetFile(file);
            }
        },

        handleDrop(event) {
            this.dragover = false;
            const file = event.dataTransfer.files[0];
            if (file) {
                this.validateAndSetFile(file);
            }
        },

        validateAndSetFile(file) {
            const allowedTypes = ['.pdf', '.docx', '.doc', '.hwp', '.hwpx'];
            const extension = '.' + file.name.split('.').pop().toLowerCase();

            if (!allowedTypes.includes(extension)) {
                this.error = '지원하지 않는 파일 형식입니다. PDF, DOCX, HWP 파일만 업로드 가능합니다.';
                return;
            }

            if (file.size > 50 * 1024 * 1024) {
                this.error = '파일 크기는 50MB를 초과할 수 없습니다.';
                return;
            }

            this.file = file;
            this.error = null;
            this.result = null;
        },

        clearFile() {
            this.file = null;
            this.$refs.fileInput.value = '';
            this.result = null;
            this.error = null;
        },

        formatFileSize(bytes) {
            if (!bytes) return '';
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        },

        async extractSchedule() {
            if (!this.file) return;

            this.loading = true;
            this.error = null;
            this.result = null;

            const formData = new FormData();
            formData.append('file', this.file);

            try {
                const response = await fetch('/api/v1/upload-and-extract', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || '일정 추출에 실패했습니다.');
                }

                this.result = data;

            } catch (err) {
                this.error = err.message;
            } finally {
                this.loading = false;
            }
        },

        getPriorityClass(priority) {
            const classes = {
                '긴급': 'bg-red-100 text-red-800',
                '높음': 'bg-orange-100 text-orange-800',
                '보통': 'bg-blue-100 text-blue-800',
                '낮음': 'bg-gray-100 text-gray-800'
            };
            return classes[priority] || classes['보통'];
        },

        getScheduleTypeClass(type) {
            const classes = {
                '착수': 'bg-green-100 text-green-800',
                '완료': 'bg-blue-100 text-blue-800',
                '설계': 'bg-purple-100 text-purple-800',
                '개발': 'bg-indigo-100 text-indigo-800',
                '테스트': 'bg-yellow-100 text-yellow-800',
                '납품': 'bg-teal-100 text-teal-800',
                '중간보고': 'bg-orange-100 text-orange-800',
                '최종보고': 'bg-red-100 text-red-800',
                '검수': 'bg-pink-100 text-pink-800',
                '인도': 'bg-cyan-100 text-cyan-800'
            };
            return classes[type] || 'bg-gray-100 text-gray-800';
        },

        exportCSV() {
            if (!this.result?.task_list) return;

            const BOM = '\uFEFF';
            const headers = ['업무ID', '업무명', '단계', '마감일', '우선순위', '상태'];
            const rows = this.result.task_list.map(t =>
                [t.task_id, t.task_name, t.phase, t.due_date || '', t.priority, t.status]
            );

            const csvContent = BOM + [headers, ...rows]
                .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
                .join('\n');

            this.downloadFile(csvContent, 'tasks.csv', 'text/csv;charset=utf-8;');
        },

        exportJSON() {
            if (!this.result) return;
            const jsonContent = JSON.stringify(this.result, null, 2);
            this.downloadFile(jsonContent, 'schedule.json', 'application/json');
        },

        exportWord() {
            if (!this.result) {
                window.toast.warning('저장할 데이터가 없습니다.');
                return;
            }

            try {
                const cs = this.result.contract_schedule;
                const contractName = cs?.contract_name || '계약서';
                let bodyHtml = '';

                if (this.result.raw_text) {
                    // 원문 텍스트가 있는 경우
                    bodyHtml = this.result.raw_text.split('\n').map(line =>
                        line.trim() ? `<p>${line.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</p>` : '<p>&nbsp;</p>'
                    ).join('\n');
                } else {
                    // 원문 없음 (스캔 PDF 등) — 구조화된 데이터로 문서 생성
                    bodyHtml = `<h2>계약 개요</h2>
                        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;">
                            <tr><td style="background:#f3f4f6; width:30%;"><b>계약명</b></td><td>${contractName}</td></tr>
                            <tr><td style="background:#f3f4f6;"><b>발주처</b></td><td>${cs?.client || '-'}</td></tr>
                            <tr><td style="background:#f3f4f6;"><b>수급자</b></td><td>${cs?.contractor || '-'}</td></tr>
                            <tr><td style="background:#f3f4f6;"><b>계약 기간</b></td><td>${cs?.contract_start_date || '미정'} ~ ${cs?.contract_end_date || '미정'}</td></tr>
                            <tr><td style="background:#f3f4f6;"><b>총 기간</b></td><td>${cs?.total_duration_days ? cs.total_duration_days + '일' : '-'}</td></tr>
                        </table>`;

                    if (cs?.schedules?.length) {
                        bodyHtml += `<h2 style="margin-top:20pt;">일정</h2>
                            <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;">
                                <tr style="background:#f3f4f6;">
                                    <th>단계</th><th>유형</th><th>시작일</th><th>종료일</th><th>설명</th>
                                </tr>
                                ${cs.schedules.map(s => `<tr>
                                    <td>${s.phase || '-'}</td>
                                    <td>${s.schedule_type || '-'}</td>
                                    <td>${s.start_date || '-'}</td>
                                    <td>${s.end_date || '-'}</td>
                                    <td>${s.description || '-'}</td>
                                </tr>`).join('')}
                            </table>`;
                    }

                    if (this.result.task_list?.length) {
                        bodyHtml += `<h2 style="margin-top:20pt;">업무 목록</h2>
                            <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;">
                                <tr style="background:#f3f4f6;">
                                    <th>업무명</th><th>단계</th><th>마감일</th><th>우선순위</th><th>상태</th>
                                </tr>
                                ${this.result.task_list.map(t => `<tr>
                                    <td>${t.task_name || '-'}</td>
                                    <td>${t.phase || '-'}</td>
                                    <td>${t.due_date || '-'}</td>
                                    <td>${t.priority || '-'}</td>
                                    <td>${t.status || '-'}</td>
                                </tr>`).join('')}
                            </table>`;
                    }
                }

                const htmlContent = `
                    <html xmlns:o="urn:schemas-microsoft-com:office:office"
                          xmlns:w="urn:schemas-microsoft-com:office:word"
                          xmlns="http://www.w3.org/TR/REC-html40">
                    <head>
                        <meta charset="utf-8">
                        <title>${contractName}</title>
                        <style>
                            body { font-family: '맑은 고딕', 'Malgun Gothic', sans-serif; font-size: 11pt; line-height: 1.6; }
                            h1 { font-size: 18pt; font-weight: bold; margin-bottom: 20pt; }
                            h2 { font-size: 14pt; font-weight: bold; margin-top: 16pt; margin-bottom: 8pt; }
                            p { margin: 6pt 0; }
                            table { font-size: 10pt; }
                            th { text-align: left; }
                        </style>
                    </head>
                    <body>
                        <h1>${contractName}</h1>
                        ${bodyHtml}
                    </body>
                    </html>
                `;

                const blob = new Blob(['\ufeff' + htmlContent], {
                    type: 'application/msword;charset=utf-8'
                });
                const fileName = `${contractName.replace(/[^a-zA-Z0-9가-힣\s]/g, '_')}.doc`;

                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = fileName;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);

            } catch (err) {
                console.error('워드 파일 생성 실패:', err);
                window.toast.error('워드 파일 생성에 실패했습니다: ' + err.message);
            }
        },

        downloadFile(content, filename, mimeType) {
            const blob = new Blob([content], { type: mimeType });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        },

        addTask() {
            if (!this.result) return;
            if (!this.result.task_list) this.result.task_list = [];

            const newId = this.result.task_list.length + 1;
            this.result.task_list.push({
                task_id: `TASK-${String(newId).padStart(3, '0')}`,
                task_name: '새 업무',
                phase: '',
                due_date: '',
                priority: '보통',
                status: '대기'
            });
        },

        deleteTask(index) {
            if (!this.result?.task_list) return;
            this.result.task_list.splice(index, 1);
        },

        addSchedule() {
            if (!this.result?.contract_schedule) return;
            if (!this.result.contract_schedule.schedules) this.result.contract_schedule.schedules = [];

            this.result.contract_schedule.schedules.push({
                phase: '새 단계',
                schedule_type: '기타',
                start_date: '',
                end_date: '',
                description: '',
                deliverables: []
            });
        },

        deleteSchedule(index) {
            if (!this.result?.contract_schedule?.schedules) return;
            this.result.contract_schedule.schedules.splice(index, 1);
        },

        async saveContract() {
            if (!this.result) {
                window.toast.warning('저장할 계약 정보가 없습니다.');
                return;
            }

            this.saveLoading = true;

            try {
                const cs = this.result.contract_schedule;
                const contractData = {
                    contract_name: cs?.contract_name || '제목 없음',
                    team_id: this.selectedTeamId || null,
                    file_name: this.file?.name || null,
                    company_name: cs?.company_name || null,
                    contractor: cs?.contractor || null,
                    client: cs?.client || null,
                    contract_date: cs?.contract_date || null,
                    contract_start_date: cs?.contract_start_date || null,
                    contract_end_date: cs?.contract_end_date || null,
                    total_duration_days: cs?.total_duration_days || null,
                    contract_amount: cs?.contract_amount || null,
                    payment_method: cs?.payment_method || null,
                    payment_due_date: cs?.payment_due_date || null,
                    schedules: cs?.schedules || [],
                    tasks: this.result.task_list || [],
                    milestones: cs?.milestones || [],
                    raw_text: this.result.raw_text || null
                };

                const response = await fetch('/api/v1/contracts/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(contractData)
                });

                if (response.ok) {
                    window.toast.success('계약이 저장되었습니다.');
                } else if (response.status === 401) {
                    window.toast.warning('로그인이 필요합니다.');
                } else if (response.status === 409) {
                    window.toast.warning('동일한 이름의 계약서가 이미 존재합니다.');
                } else {
                    const data = await response.json().catch(() => null);
                    throw new Error(data?.detail || `서버 오류 (${response.status})`);
                }
            } catch (err) {
                window.toast.error('저장 실패: ' + err.message);
            } finally {
                this.saveLoading = false;
            }
        },

        loadContractData(contract) {
            // 저장된 계약 데이터를 result 형식으로 변환
            this.result = {
                contract_schedule: {
                    contract_name: contract.contract_name,
                    company_name: contract.company_name,
                    contractor: contract.contractor,
                    client: contract.client,
                    contract_date: contract.contract_date,
                    contract_start_date: contract.contract_start_date,
                    contract_end_date: contract.contract_end_date,
                    total_duration_days: contract.total_duration_days,
                    contract_amount: contract.contract_amount,
                    payment_method: contract.payment_method,
                    payment_due_date: contract.payment_due_date,
                    schedules: contract.schedules || [],
                    milestones: contract.milestones || []
                },
                task_list: contract.tasks || [],
                raw_text: contract.raw_text || null
            };
            this.file = null;
            this.error = null;

            // 페이지 상단으로 스크롤
            window.scrollTo({ top: 0, behavior: 'smooth' });
        },

        async loadMyContracts() {
            this.myContractsLoading = true;
            this.contractFilterYear = '';
            this.contractFilterMonth = '';
            try {
                const params = this.selectedTeamId ? `?team_id=${this.selectedTeamId}` : '';
                const response = await fetch(`/api/v1/contracts/list${params}`);
                if (response.ok) {
                    const data = await response.json();
                    this.myContracts = data.items || data;
                }
            } catch (err) {
                console.error('계약 목록 로드 실패:', err);
            } finally {
                this.myContractsLoading = false;
            }
        },

        get contractYears() {
            const years = new Set();
            this.myContracts.forEach(c => {
                if (c.created_at) years.add(new Date(c.created_at).getFullYear());
            });
            return [...years].sort((a, b) => b - a);
        },

        get contractMonths() {
            const months = new Set();
            this.myContracts.forEach(c => {
                if (!c.created_at) return;
                const d = new Date(c.created_at);
                if (this.contractFilterYear && d.getFullYear() !== parseInt(this.contractFilterYear)) return;
                months.add(d.getMonth() + 1);
            });
            return [...months].sort((a, b) => a - b);
        },

        get filteredContracts() {
            return this.myContracts.filter(c => {
                if (!c.created_at) return true;
                const d = new Date(c.created_at);
                if (this.contractFilterYear && d.getFullYear() !== parseInt(this.contractFilterYear)) return false;
                if (this.contractFilterMonth && (d.getMonth() + 1) !== parseInt(this.contractFilterMonth)) return false;
                return true;
            });
        },

        async deleteContract(contractId) {
            if (!confirm('이 계약을 삭제하시겠습니까?')) return;

            try {
                const response = await fetch(`/api/v1/contracts/${contractId}`, {
                    method: 'DELETE'
                });
                if (response.ok) {
                    this.myContracts = this.myContracts.filter(c => c.id !== contractId);
                }
            } catch (err) {
                console.error('계약 삭제 실패:', err);
            }
        },

        loadContract(contract) {
            this.loadContractData(contract);
            this.showMyPage = false;
            this._dispatchPage('upload');
        },

        openAddTask() {
            this.newTask = {
                contract_id: '',
                task_name: '',
                phase: '',
                due_date: '',
                priority: '보통',
                status: '대기',
                assignee_id: '',
            };
            this.showAddTask = true;
        },

        async submitNewTask() {
            if (!this.newTask.task_name.trim()) {
                window.toast.warning('업무명을 입력해주세요.');
                return;
            }

            this.addTaskLoading = true;
            try {
                const response = await fetch('/api/v1/contracts/tasks/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        contract_id: this.newTask.contract_id || null,
                        task_name: this.newTask.task_name,
                        phase: this.newTask.phase,
                        due_date: this.newTask.due_date,
                        priority: this.newTask.priority,
                        status: this.newTask.status,
                        assignee_id: this.newTask.assignee_id || null,
                    })
                });

                if (!response.ok) {
                    const data = await response.json();
                    const detail = data.detail;
                    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
                }

                const data = await response.json();

                // 대시보드에 새 업무 추가
                if (this.dashboard) {
                    if (!this.dashboard.tasks) this.dashboard.tasks = [];
                    this.dashboard.tasks.push(data.task);
                    this.dashboard.total_tasks = this.dashboard.tasks.length;
                    this.dashboard.pending_tasks = this.dashboard.tasks.filter(t => t.status === '대기').length;
                    this.dashboard.in_progress_tasks = this.dashboard.tasks.filter(t => t.status === '진행중').length;
                    this.dashboard.completed_tasks = this.dashboard.tasks.filter(t => t.status === '완료').length;
                }

                this.showAddTask = false;
            } catch (err) {
                window.toast.error('업무 추가 실패: ' + err.message);
            } finally {
                this.addTaskLoading = false;
            }
        },

        async updateTaskStatus(contractId, taskId, newStatus) {
            try {
                const response = await fetch(`/api/v1/contracts/${contractId}/tasks/status`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ task_id: String(taskId), status: newStatus })
                });

                if (!response.ok) {
                    const data = await response.json();
                    const detail = data.detail;
                    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail);
                    throw new Error(msg || '상태 변경 실패');
                }

                // 대시보드 데이터 갱신
                if (this.dashboard?.tasks) {
                    const task = this.dashboard.tasks.find(
                        t => t.contract_id === contractId && t.task_id === taskId
                    );
                    if (task) task.status = newStatus;

                    // 통계 재계산
                    this.dashboard.pending_tasks = this.dashboard.tasks.filter(t => t.status === '대기').length;
                    this.dashboard.in_progress_tasks = this.dashboard.tasks.filter(t => t.status === '진행중').length;
                    this.dashboard.completed_tasks = this.dashboard.tasks.filter(t => t.status === '완료').length;
                }
            } catch (err) {
                window.toast.error('상태 변경 실패: ' + err.message);
            }
        },

        async saveTaskNote(contractId, taskId, note) {
            try {
                const response = await fetch(`/api/v1/contracts/${contractId}/tasks/note`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ task_id: String(taskId), note })
                });

                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || '저장 실패');
                }

                // 로컬 데이터 업데이트
                if (this.dashboard?.tasks) {
                    const task = this.dashboard.tasks.find(
                        t => t.contract_id === contractId && t.task_id === taskId
                    );
                    if (task) task.note = note;
                }
            } catch (err) {
                window.toast.error('처리 내용 저장 실패: ' + err.message);
            }
        },

        async uploadAttachment(contractId, taskId, event) {
            const file = event.target.files[0];
            if (!file) return;

            if (file.size > 20 * 1024 * 1024) {
                window.toast.warning('파일 크기는 20MB를 초과할 수 없습니다.');
                return;
            }

            const formData = new FormData();
            formData.append('task_id', String(taskId));
            formData.append('file', file);

            try {
                const response = await fetch(`/api/v1/contracts/${contractId}/tasks/attachment`, {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || '업로드 실패');
                }

                const data = await response.json();

                // 로컬 데이터 업데이트
                if (this.dashboard?.tasks) {
                    const task = this.dashboard.tasks.find(
                        t => t.contract_id === contractId && t.task_id === taskId
                    );
                    if (task) {
                        if (!task.attachments) task.attachments = [];
                        task.attachments.push(data.attachment);
                    }
                }
            } catch (err) {
                window.toast.error('파일 업로드 실패: ' + err.message);
            }

            // input 초기화
            event.target.value = '';
        },

        // ============ 댓글 시스템 ============
        comments: [],
        commentsLoading: false,
        newComment: '',
        activeCommentContract: null,
        activeCommentTask: null,

        async loadComments(contractId, taskId = null) {
            this.commentsLoading = true;
            this.activeCommentContract = contractId;
            this.activeCommentTask = taskId;
            try {
                const params = taskId ? `?task_id=${encodeURIComponent(taskId)}` : '';
                const res = await fetch(`/api/v1/contracts/${contractId}/comments${params}`);
                if (res.ok) this.comments = await res.json();
            } catch (err) { console.error('댓글 로드 실패:', err); }
            finally { this.commentsLoading = false; }
        },

        async submitComment() {
            if (!this.newComment.trim() || !this.activeCommentContract) return;
            try {
                const res = await fetch(`/api/v1/contracts/${this.activeCommentContract}/comments`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        content: this.newComment,
                        task_id: this.activeCommentTask,
                    })
                });
                if (res.ok) {
                    const comment = await res.json();
                    this.comments.push(comment);
                    this.newComment = '';
                }
            } catch (err) { window.toast.error('댓글 작성 실패'); }
        },

        async deleteComment(contractId, commentId) {
            if (!confirm('이 댓글을 삭제하시겠습니까?')) return;
            try {
                const res = await fetch(`/api/v1/contracts/${contractId}/comments/${commentId}`, { method: 'DELETE' });
                if (res.ok) {
                    this.comments = this.comments.filter(c => c.id !== commentId);
                }
            } catch (err) { window.toast.error('댓글 삭제 실패'); }
        },

        // ============ 활동 로그 ============
        activityLogs: [],
        activityLoading: false,
        showActivityLog: false,

        async loadActivityLogs(contractId = null) {
            this.activityLoading = true;
            try {
                let params = '';
                if (contractId) params = `?contract_id=${contractId}`;
                else if (this.selectedTeamId) params = `?team_id=${this.selectedTeamId}`;
                const res = await fetch(`/api/v1/activity${params}`);
                if (res.ok) {
                    const data = await res.json();
                    this.activityLogs = data.items || [];
                }
            } catch (err) { console.error('활동 로그 로드 실패:', err); }
            finally { this.activityLoading = false; }
        },

        getActionLabel(action) {
            const labels = {
                'create': '생성',
                'update': '수정',
                'delete': '삭제',
                'assign': '담당자 지정',
                'status_change': '상태 변경',
                'comment': '댓글',
                'invite': '멤버 초대',
                'remove': '멤버 제거',
                'change_role': '역할 변경',
            };
            return labels[action] || action;
        },

        getActionColor(action) {
            const colors = {
                'create': 'text-green-600',
                'update': 'text-blue-600',
                'delete': 'text-red-600',
                'assign': 'text-purple-600',
                'status_change': 'text-orange-600',
                'comment': 'text-gray-600',
                'invite': 'text-indigo-600',
                'remove': 'text-red-500',
                'change_role': 'text-yellow-600',
            };
            return colors[action] || 'text-gray-600';
        },

        // ============ 권한 확인 ============
        teamPermissions: [],

        async loadPermissions(teamId) {
            if (!teamId) { this.teamPermissions = []; return; }
            try {
                const res = await fetch(`/api/v1/teams/${teamId}/permissions`);
                if (res.ok) {
                    const data = await res.json();
                    this.teamPermissions = data.permissions || [];
                }
            } catch (err) { this.teamPermissions = []; }
        },

        hasPermission(perm) {
            // 개인 모드에서는 항상 허용
            if (!this.selectedTeamId) return true;
            return this.teamPermissions.includes(perm);
        },

        async deleteAttachment(contractId, taskId, filename) {
            if (!confirm('이 파일을 삭제하시겠습니까?')) return;

            try {
                const response = await fetch(
                    `/api/v1/contracts/${contractId}/tasks/attachment?task_id=${encodeURIComponent(taskId)}&filename=${encodeURIComponent(filename)}`,
                    { method: 'DELETE' }
                );

                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || '삭제 실패');
                }

                // 로컬 데이터 업데이트
                if (this.dashboard?.tasks) {
                    const task = this.dashboard.tasks.find(
                        t => t.contract_id === contractId && t.task_id === taskId
                    );
                    if (task?.attachments) {
                        task.attachments = task.attachments.filter(a => a.filename !== filename);
                    }
                }
            } catch (err) {
                window.toast.error('파일 삭제 실패: ' + err.message);
            }
        }
    };
}

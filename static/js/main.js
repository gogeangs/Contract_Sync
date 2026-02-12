function authState() {
    return {
        user: null,
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

        async init() {
            await this.checkAuth();
        },

        async checkAuth() {
            try {
                const response = await fetch('/api/v1/auth/me');
                const data = await response.json();

                if (data.logged_in && data.user) {
                    this.user = data.user;
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
        showMyPage: false,
        myContracts: [],
        myContractsLoading: false,

        // 로그인 상태
        isLoggedIn: false,

        // 대시보드 상태
        showDashboard: false,
        dashboard: null,
        dashboardLoading: false,
        taskFilter: 'all', // all, pending, in_progress, completed

        // 업무 추가 폼
        showAddTask: false,
        newTask: {
            contract_id: null,
            task_name: '',
            phase: '',
            due_date: '',
            priority: '보통',
            status: '대기'
        },
        addTaskLoading: false,

        init() {
            // 이벤트 리스너는 HTML에서 처리
        },

        async loadDashboard() {
            this.dashboardLoading = true;
            try {
                const response = await fetch('/api/v1/contracts/dashboard/summary');
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

        get filteredTasks() {
            if (!this.dashboard?.tasks) return [];
            if (this.taskFilter === 'all') return this.dashboard.tasks;
            const statusMap = {
                'pending': '대기',
                'in_progress': '진행중',
                'completed': '완료'
            };
            return this.dashboard.tasks.filter(t => t.status === statusMap[this.taskFilter]);
        },

        goToUpload() {
            this.showDashboard = false;
            this.showMyPage = false;
            this.result = null;
            this.file = null;
            this.error = null;
            this.editMode = false;
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
                alert('저장할 데이터가 없습니다.');
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
                alert('워드 파일 생성에 실패했습니다: ' + err.message);
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
                alert('저장할 계약 정보가 없습니다.');
                return;
            }

            this.saveLoading = true;

            try {
                const contractData = {
                    contract_name: this.result.contract_schedule?.contract_name || '제목 없음',
                    file_name: this.file?.name || null,
                    contractor: this.result.contract_schedule?.contractor || null,
                    client: this.result.contract_schedule?.client || null,
                    contract_start_date: this.result.contract_schedule?.contract_start_date || null,
                    contract_end_date: this.result.contract_schedule?.contract_end_date || null,
                    total_duration_days: this.result.contract_schedule?.total_duration_days || null,
                    schedules: this.result.contract_schedule?.schedules || [],
                    tasks: this.result.task_list || [],
                    milestones: this.result.contract_schedule?.milestones || [],
                    raw_text: this.result.raw_text || null
                };

                const response = await fetch('/api/v1/contracts/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(contractData)
                });

                if (response.ok) {
                    alert('계약이 저장되었습니다.');
                } else if (response.status === 401) {
                    alert('로그인이 필요합니다.');
                } else if (response.status === 409) {
                    alert('동일한 이름의 계약서가 이미 존재합니다.');
                } else {
                    const text = await response.text();
                    try {
                        const data = JSON.parse(text);
                        throw new Error(data.detail || '저장 실패');
                    } catch {
                        throw new Error(`서버 오류 (${response.status})`);
                    }
                }
            } catch (err) {
                alert('저장 실패: ' + err.message);
            } finally {
                this.saveLoading = false;
            }
        },

        loadContractData(contract) {
            // 저장된 계약 데이터를 result 형식으로 변환
            this.result = {
                contract_schedule: {
                    contract_name: contract.contract_name,
                    contractor: contract.contractor,
                    client: contract.client,
                    contract_start_date: contract.contract_start_date,
                    contract_end_date: contract.contract_end_date,
                    total_duration_days: contract.total_duration_days,
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
            try {
                const response = await fetch('/api/v1/contracts/list');
                if (response.ok) {
                    this.myContracts = await response.json();
                }
            } catch (err) {
                console.error('계약 목록 로드 실패:', err);
            } finally {
                this.myContractsLoading = false;
            }
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
        },

        openAddTask() {
            this.newTask = {
                contract_id: '',
                task_name: '',
                phase: '',
                due_date: '',
                priority: '보통',
                status: '대기'
            };
            this.showAddTask = true;
        },

        async submitNewTask() {
            if (!this.newTask.task_name.trim()) {
                alert('업무명을 입력해주세요.');
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
                        status: this.newTask.status
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
                alert('업무 추가 실패: ' + err.message);
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
                alert('상태 변경 실패: ' + err.message);
            }
        }
    };
}

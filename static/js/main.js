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
                }
            } catch (err) {
                console.error('인증 확인 실패:', err);
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
        }
    };
}

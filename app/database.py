from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text,
    ForeignKey, JSON, UniqueConstraint, Index,
)
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> datetime:
    """SQLite 호환 naive UTC 현재 시각 반환"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Railway Volume 마운트 지원: DATA_DIR 환경변수 설정 시 해당 경로에 DB 저장
from app.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent
if settings.data_dir:
    _data_dir = Path(settings.data_dir)
    _data_dir.mkdir(parents=True, exist_ok=True)
    DB_PATH = _data_dir / "contract_sync.db"
else:
    DB_PATH = BASE_DIR / "contract_sync.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Railway Volume에서 SQLite 안정성을 위한 pragma 설정
from sqlalchemy import event

@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


class Base(DeclarativeBase):
    pass


# ══════════════════════════════════════════════════════════
#  1. 사용자 / 인증  (기존 유지)
# ══════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    auth_provider = Column(String, default="email")  # email / google
    user_type = Column(String(20), default="human")  # human / ai_agent
    created_at = Column(DateTime, default=utc_now)


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", backref="sessions")


# ══════════════════════════════════════════════════════════
#  1-1. AI 챗봇 대화  [3차 개발]
# ══════════════════════════════════════════════════════════

class ChatSession(Base):
    """챗봇 대화 세션"""
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", backref="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                            order_by="ChatMessage.created_at")


class ChatMessage(Base):
    """챗봇 대화 메시지"""
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_message_session", "chat_session_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    chat_session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    message_type = Column(String(20), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    session = relationship("ChatSession", back_populates="messages")


# ══════════════════════════════════════════════════════════
#  2. 팀 관리  (기존 유지)
# ══════════════════════════════════════════════════════════

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=utc_now)

    creator = relationship("User", backref="created_teams")
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, default="member")  # owner, admin, member, viewer
    joined_at = Column(DateTime, default=utc_now)

    team = relationship("Team", back_populates="members")
    user = relationship("User", backref="team_memberships")


# ══════════════════════════════════════════════════════════
#  3. 발주처(클라이언트)  [신규]
# ══════════════════════════════════════════════════════════

class Client(Base):
    """발주처 — 프로젝트의 업무 의뢰 주체"""
    __tablename__ = "clients"
    __table_args__ = (
        Index("ix_client_team_user", "team_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(200), nullable=False)
    contact_name = Column(String(100), nullable=True)
    contact_email = Column(String(200), nullable=True)
    contact_phone = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", backref="clients")
    team = relationship("Team", backref="clients")
    projects = relationship("Project", back_populates="client")
    portal_tokens = relationship("PortalToken", back_populates="client")


# ══════════════════════════════════════════════════════════
#  4. 프로젝트  (기존 Contract 확장·리네임)
# ══════════════════════════════════════════════════════════

class Project(Base):
    """프로젝트 — 업무·문서·보고서·수금의 상위 컨테이너
    v1 Contract 테이블을 확장하여 리네임한 것.
    """
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)

    # ── v2 핵심 필드 ──
    project_name = Column(String(500), nullable=False)
    project_type = Column(String(20), default="outsourcing")  # outsourcing / internal / maintenance
    status = Column(String(20), default="planning")  # planning / active / on_hold / completed / cancelled
    description = Column(Text, nullable=True)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    total_duration_days = Column(Integer, nullable=True)
    contract_amount = Column(String(200), nullable=True)
    payment_method = Column(String(500), nullable=True)
    schedules = Column(JSON, nullable=True)
    milestones = Column(JSON, nullable=True)

    # ── Figma 연동 (3차 개발) ──
    figma_urls = Column(JSON, nullable=True)  # ["https://figma.com/design/..."]

    # ── AI 정기보고 설정 ──
    report_opt_in = Column(Boolean, default=False)
    report_frequency = Column(String(10), nullable=True)  # daily / weekly / monthly

    # ── v1 호환 필드 (contracts.py deprecated API 제거 시 함께 삭제) ──
    contract_name = Column(String(500), nullable=True)  # → project_name
    file_name = Column(String, nullable=True)            # contracts.py 전용
    company_name = Column(String, nullable=True)         # contracts.py 전용
    contractor = Column(String, nullable=True)           # contracts.py 전용
    contract_date = Column(String, nullable=True)        # contracts.py 전용
    contract_start_date = Column(String, nullable=True)  # contracts.py 전용
    contract_end_date = Column(String, nullable=True)    # contracts.py 전용
    payment_due_date = Column(String, nullable=True)     # contracts.py 전용
    raw_text = Column(Text, nullable=True)               # contracts.py 전용
    tasks_json = Column("tasks", JSON, nullable=True)    # contracts.py 전용 (→ tasks 테이블)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # relationships
    user = relationship("User", backref="projects")
    team = relationship("Team", backref="projects")
    client = relationship("Client", back_populates="projects")
    task_list = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="project")
    ai_reports = relationship("AIReport", back_populates="project", cascade="all, delete-orphan")
    payment_schedules = relationship("PaymentSchedule", back_populates="project", cascade="all, delete-orphan")
    recurring_tasks = relationship("RecurringTask", back_populates="project", cascade="all, delete-orphan")


# v1 코드 호환용 별칭
Contract = Project


# ══════════════════════════════════════════════════════════
#  5. 업무  [신규 — 독립 테이블]
# ══════════════════════════════════════════════════════════

class Task(Base):
    """업무 — 독립 테이블. project_id NULLABLE (프로젝트 없이도 생성 가능)"""
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_task_project", "project_id"),
        Index("ix_task_assignee", "assignee_id"),
        Index("ix_task_status", "status"),
        Index("ix_task_due_date", "due_date"),
        Index("ix_task_team_status", "team_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_code = Column(String(20), nullable=True)  # TASK-001 형식
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    task_name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    phase = Column(String(200), nullable=True)
    status = Column(String(20), default="pending")
    # pending / in_progress / completed / report_sent / feedback_pending / confirmed / revision_requested
    priority = Column(String(10), default="보통")  # 긴급 / 높음 / 보통 / 낮음
    due_date = Column(String, nullable=True)
    start_date = Column(String, nullable=True)
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_client_facing = Column(Boolean, default=False)
    note = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    source = Column(String(30), nullable=True)  # None=manual, "google_calendar", etc.
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # relationships
    project = relationship("Project", back_populates="task_list")
    user = relationship("User", foreign_keys=[user_id], backref="created_tasks")
    assignee = relationship("User", foreign_keys=[assignee_id], backref="assigned_tasks")
    team = relationship("Team", backref="tasks")
    attachments = relationship("TaskAttachment", back_populates="task", cascade="all, delete-orphan")
    completion_reports = relationship("CompletionReport", back_populates="task", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="task")


class TaskAttachment(Base):
    """업무 산출물(증빙파일)"""
    __tablename__ = "task_attachments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(500), nullable=False)
    stored_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    task = relationship("Task", back_populates="attachments")
    uploader = relationship("User", backref="uploaded_attachments")


# ══════════════════════════════════════════════════════════
#  6. 문서 관리  (기존 contract_id → project_id)
# ══════════════════════════════════════════════════════════

class Document(Base):
    """프로젝트 문서 (견적서/계약서/제안서/기타)"""
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_document_project_type", "project_id", "document_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    document_type = Column(String(20), nullable=False)  # estimate / contract / proposal / other
    title = Column(String(300), nullable=False)
    file_name = Column(String(500), nullable=True)
    stored_path = Column(String(500), nullable=True)
    status = Column(String(20), default="uploaded")
    # uploaded / analyzing / review_pending / revision_requested / confirmed
    version = Column(Integer, default=1)
    parent_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    ai_analysis = Column(JSON, nullable=True)
    raw_text = Column(Text, nullable=True)
    google_sheet_id = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    project = relationship("Project", back_populates="documents")
    user = relationship("User", backref="documents")
    parent = relationship("Document", remote_side="Document.id", backref="versions")
    reviews = relationship("DocumentReview", back_populates="document", cascade="all, delete-orphan")


# ══════════════════════════════════════════════════════════
#  8. 문서 검토  (기존 유지)
# ══════════════════════════════════════════════════════════

class DocumentReview(Base):
    """문서 검토"""
    __tablename__ = "document_reviews"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="pending")  # pending / approved / rejected / commented
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    reviewed_at = Column(DateTime, nullable=True)

    document = relationship("Document", back_populates="reviews")
    reviewer = relationship("User", backref="document_reviews")


# ══════════════════════════════════════════════════════════
#  9. 완료 보고  [신규]
# ══════════════════════════════════════════════════════════

class CompletionReport(Base):
    """완료 보고 — 발주처 대면 업무 완료 시 이메일 발송"""
    __tablename__ = "completion_reports"
    __table_args__ = (
        Index("ix_completion_report_task", "task_id"),
        Index("ix_completion_report_token", "feedback_token"),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipient_email = Column(String(200), nullable=False)
    cc_emails = Column(JSON, nullable=True)
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)
    attachments = Column(JSON, nullable=True)  # [{file_name, stored_path, file_size}]
    feedback_token = Column(String(64), unique=True, nullable=True)
    feedback_token_expires_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="draft")  # draft / scheduled / sent / failed
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    task = relationship("Task", back_populates="completion_reports")
    project = relationship("Project")
    sender = relationship("User", backref="sent_reports")
    feedbacks = relationship("ClientFeedback", back_populates="completion_report", cascade="all, delete-orphan")


# ══════════════════════════════════════════════════════════
# 10. 클라이언트 피드백  [신규]
# ══════════════════════════════════════════════════════════

class ClientFeedback(Base):
    """발주처 피드백 — 비로그인 토큰 기반"""
    __tablename__ = "client_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    completion_report_id = Column(Integer, ForeignKey("completion_reports.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    feedback_type = Column(String(20), nullable=False)  # confirmed / revision / comment
    content = Column(Text, nullable=True)
    client_name = Column(String(100), nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    completion_report = relationship("CompletionReport", back_populates="feedbacks")
    task = relationship("Task", backref="feedbacks")


# ══════════════════════════════════════════════════════════
# 10-1. 고객 피드백 요청/응답  [3차 개발]
# ══════════════════════════════════════════════════════════

class FeedbackRequest(Base):
    """고객 피드백 요청 — PM이 시안 확인 요청 발송"""
    __tablename__ = "feedback_requests"
    __table_args__ = (
        Index("ix_feedback_request_project", "project_id"),
        Index("ix_feedback_request_token", "feedback_token"),
        Index("ix_feedback_request_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipient_email = Column(String(200), nullable=False)
    subject = Column(String(500), nullable=False)
    message = Column(Text, nullable=True)
    attachments = Column(JSON, nullable=True)  # [{file_name, stored_path}]
    figma_url = Column(Text, nullable=True)
    feedback_token = Column(String(64), unique=True, nullable=False)
    feedback_deadline = Column(String, nullable=True)  # YYYY-MM-DD
    status = Column(String(20), default="sent")  # sent / viewed / responded / expired / cancelled
    viewed_at = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    reminder_count = Column(Integer, default=0)
    last_reminder_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    project = relationship("Project", backref="feedback_requests")
    sender = relationship("User", backref="sent_feedback_requests")
    responses = relationship("FeedbackResponse", back_populates="feedback_request", cascade="all, delete-orphan")


class FeedbackResponse(Base):
    """고객 피드백 응답 — 비로그인 고객이 포털에서 제출"""
    __tablename__ = "feedback_responses"

    id = Column(Integer, primary_key=True, index=True)
    feedback_request_id = Column(Integer, ForeignKey("feedback_requests.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    response_type = Column(String(30), nullable=False)  # approved / revision_requested / comment
    content = Column(Text, nullable=True)
    client_name = Column(String(100), nullable=True)
    client_phone = Column(String(20), nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    feedback_request = relationship("FeedbackRequest", back_populates="responses")
    project = relationship("Project", backref="feedback_responses")


# ══════════════════════════════════════════════════════════
# 10-2. 알림톡 발송 이력  [3차 개발 — 선택]
# ══════════════════════════════════════════════════════════

class KakaoNotification(Base):
    """카카오 알림톡 발송 이력"""
    __tablename__ = "kakao_notifications"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    feedback_request_id = Column(Integer, ForeignKey("feedback_requests.id", ondelete="SET NULL"), nullable=True)
    template_code = Column(String(50), nullable=False)
    recipient_phone = Column(String(20), nullable=False)
    variables = Column(JSON, nullable=True)  # 템플릿 변수
    status = Column(String(20), default="pending")  # pending / sent / delivered / failed
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    project = relationship("Project", backref="kakao_notifications")


# ══════════════════════════════════════════════════════════
# 10-3. MCP 추천  [3차 개발 — 선택]
# ══════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════
#  4차 개발 — Phase 1: 게시판
# ══════════════════════════════════════════════════════════

class Board(Base):
    """게시판 — 팀별 또는 개인 게시판 (공지/자유/자료)"""
    __tablename__ = "boards"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)  # notice / free / archive
    created_at = Column(DateTime, default=utc_now)

    team = relationship("Team", backref="boards")
    owner = relationship("User", backref="owned_boards", foreign_keys=[user_id])
    posts = relationship("BoardPost", back_populates="board", cascade="all, delete-orphan")


class BoardPost(Base):
    """게시글"""
    __tablename__ = "board_posts"
    __table_args__ = (
        Index("ix_board_post_board", "board_id"),
        Index("ix_board_post_author", "author_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    board_id = Column(Integer, ForeignKey("boards.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    is_pinned = Column(Boolean, default=False)
    view_count = Column(Integer, default=0)
    file_urls = Column(JSON, nullable=True)  # [{name, url, size}]
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    board = relationship("Board", back_populates="posts")
    author = relationship("User", backref="board_posts")
    comments = relationship("BoardComment", back_populates="post", cascade="all, delete-orphan")


class BoardComment(Base):
    """게시글 댓글"""
    __tablename__ = "board_comments"
    __table_args__ = (
        Index("ix_board_comment_post", "post_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("board_posts.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    post = relationship("BoardPost", back_populates="comments")
    author = relationship("User", backref="board_comments")


# ══════════════════════════════════════════════════════════
#  4차 개발 — Phase 1: 이메일 초대
# ══════════════════════════════════════════════════════════

class PendingInvite(Base):
    """대기 초대 — 미가입 사용자 이메일 초대"""
    __tablename__ = "pending_invites"
    __table_args__ = (
        Index("ix_pending_invite_token", "token"),
        Index("ix_pending_invite_email", "email"),
    )

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), nullable=False)
    role = Column(String(20), default="member")  # member / admin
    token = Column(String(64), unique=True, nullable=False)
    invited_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="pending")  # pending / accepted / expired
    created_at = Column(DateTime, default=utc_now)
    expires_at = Column(DateTime, nullable=False)

    team = relationship("Team", backref="pending_invites")
    inviter = relationship("User", backref="sent_invites")


# ══════════════════════════════════════════════════════════
#  4차 개발 — Phase 2: 멀티팀 우선업무
# ══════════════════════════════════════════════════════════

class UserTaskPriority(Base):
    """개인 업무 우선순위 — 멀티팀 통합 정렬"""
    __tablename__ = "user_task_priorities"
    __table_args__ = (
        UniqueConstraint("user_id", "task_id", name="uq_user_task_priority"),
        Index("ix_user_task_priority_user", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", backref="task_priorities")
    task = relationship("Task", backref="user_priorities")


# ══════════════════════════════════════════════════════════
#  4차 개발 — Phase 3: 멤버 간 채팅
# ══════════════════════════════════════════════════════════

class ChatRoom(Base):
    """채팅방 — 1:1 / 그룹 / 프로젝트"""
    __tablename__ = "chat_rooms"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=True)  # 그룹 채팅방 이름
    type = Column(String(20), nullable=False)  # direct / group / project
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    team = relationship("Team", backref="chat_rooms")
    project = relationship("Project", backref="chat_rooms")
    members = relationship("ChatRoomMember", back_populates="room", cascade="all, delete-orphan")
    room_messages = relationship("RoomMessage", back_populates="room", cascade="all, delete-orphan")


class ChatRoomMember(Base):
    """채팅방 참여자"""
    __tablename__ = "chat_room_members"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_chatroom_member"),
        Index("ix_chatroom_member_user", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    joined_at = Column(DateTime, default=utc_now)
    last_read_at = Column(DateTime, nullable=True)

    room = relationship("ChatRoom", back_populates="members")
    user = relationship("User", backref="chat_room_memberships")


class RoomMessage(Base):
    """채팅 메시지"""
    __tablename__ = "room_messages"
    __table_args__ = (
        Index("ix_room_message_room", "room_id"),
        Index("ix_room_message_created", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    file_urls = Column(JSON, nullable=True)  # [{name, url, size}]
    created_at = Column(DateTime, default=utc_now)

    room = relationship("ChatRoom", back_populates="room_messages")
    sender = relationship("User", backref="sent_room_messages")


# ══════════════════════════════════════════════════════════
#  4차 개발 — Phase 4: 출퇴근 기록
# ══════════════════════════════════════════════════════════

class Attendance(Base):
    """출퇴근 기록"""
    __tablename__ = "attendances"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", "date", name="uq_attendance_daily"),
        Index("ix_attendance_team_date", "team_id", "date"),
        Index("ix_attendance_user_date", "user_id", "date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    check_in = Column(String(5), nullable=True)   # HH:MM
    check_out = Column(String(5), nullable=True)   # HH:MM
    work_hours = Column(String(5), nullable=True)  # H.HH (소수점)
    status = Column(String(20), default="normal")  # normal / late / early_leave / absent
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    team = relationship("Team", backref="attendances")
    user = relationship("User", backref="attendances")


class AttendancePolicy(Base):
    """근무 정책 — 팀별 설정"""
    __tablename__ = "attendance_policies"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, unique=True)
    default_check_in = Column(String(5), default="09:00")   # HH:MM
    default_check_out = Column(String(5), default="18:00")   # HH:MM
    work_hours = Column(Integer, default=8)       # 시간 단위
    break_hours = Column(Integer, default=1)      # 시간 단위
    created_at = Column(DateTime, default=utc_now)

    team = relationship("Team", backref="attendance_policy", uselist=False)


class McpRecommendation(Base):
    """MCP 추천 — 업무 패턴 기반 MCP 도구 추천"""
    __tablename__ = "mcp_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mcp_name = Column(String(100), nullable=False)  # figma / google_calendar / google_drive / youtube
    reason = Column(Text, nullable=True)
    score = Column(Integer, default=0)  # 추천 점수
    is_dismissed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)

    team = relationship("Team", backref="mcp_recommendations")
    user = relationship("User", backref="mcp_recommendations")


# ══════════════════════════════════════════════════════════
# 11. AI 보고서  [신규]
# ══════════════════════════════════════════════════════════

class AIReport(Base):
    """AI 보고서 — 정기(periodic) / 프로젝트 완료(completion)"""
    __tablename__ = "ai_reports"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    report_type = Column(String(20), nullable=False)  # periodic / completion
    period_start = Column(String, nullable=True)
    period_end = Column(String, nullable=True)
    title = Column(String(300), nullable=False)
    content_html = Column(Text, nullable=False)
    content_json = Column(JSON, nullable=True)
    status = Column(String(20), default="draft")  # draft / sent / archived
    sent_to = Column(JSON, nullable=True)  # [email, ...]
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    project = relationship("Project", back_populates="ai_reports")


# ══════════════════════════════════════════════════════════
# 13. 수금/매출 관리  [신규]
# ══════════════════════════════════════════════════════════

class PaymentSchedule(Base):
    """결제 일정 — 프로젝트별 수금 추적"""
    __tablename__ = "payment_schedules"
    __table_args__ = (
        Index("ix_payment_project_status", "project_id", "status"),
        Index("ix_payment_due_status", "due_date", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    payment_type = Column(String(30), nullable=False)  # advance / interim / final / milestone
    description = Column(String(300), nullable=False)
    amount = Column(Integer, nullable=False)  # 원 단위
    due_date = Column(String, nullable=True)
    status = Column(String(20), default="pending")  # pending / invoiced / paid / overdue
    paid_date = Column(String, nullable=True)
    paid_amount = Column(Integer, nullable=True)
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    project = relationship("Project", back_populates="payment_schedules")
    document = relationship("Document", backref="payment_schedules")


# ══════════════════════════════════════════════════════════
# 14. 프로젝트 템플릿 / 반복 업무  [신규]
# ══════════════════════════════════════════════════════════

class ProjectTemplate(Base):
    """프로젝트 템플릿 — 업무·일정 구조를 재활용"""
    __tablename__ = "project_templates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(200), nullable=False)
    project_type = Column(String(20), nullable=False)  # outsourcing / internal / maintenance
    description = Column(Text, nullable=True)
    task_templates = Column(JSON, nullable=True)       # [{task_name, phase, relative_due_days, priority, is_client_facing}]
    schedule_templates = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", backref="project_templates")
    team = relationship("Team", backref="project_templates")


class RecurringTask(Base):
    """반복 업무 — 유지보수 프로젝트에서 자동 생성"""
    __tablename__ = "recurring_tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    task_name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    frequency = Column(String(10), nullable=False)  # daily / weekly / monthly
    day_of_month = Column(Integer, nullable=True)    # 매월 N일  (monthly)
    day_of_week = Column(Integer, nullable=True)     # 요일 0=월 (weekly)
    priority = Column(String(10), default="보통")
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True)
    last_generated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    project = relationship("Project", back_populates="recurring_tasks")
    assignee = relationship("User", backref="recurring_task_assignments")


# ══════════════════════════════════════════════════════════
# 16. 클라이언트 포털  [신규]
# ══════════════════════════════════════════════════════════

class PortalToken(Base):
    """포털 접근 토큰 — 비로그인 프로젝트 현황 조회"""
    __tablename__ = "portal_tokens"
    __table_args__ = (
        Index("ix_portal_token", "token"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(64), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

    client = relationship("Client", back_populates="portal_tokens")
    project = relationship("Project", backref="portal_tokens")


# ══════════════════════════════════════════════════════════
# 17. 캘린더 연동  [신규]
# ══════════════════════════════════════════════════════════

class CalendarSync(Base):
    """캘린더 연동 설정 — Google Calendar / Outlook"""
    __tablename__ = "calendar_syncs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(20), nullable=False)  # google / outlook
    access_token = Column(Text, nullable=True)      # crypto_service.encrypt_token() 으로 암호화 저장
    refresh_token = Column(Text, nullable=True)     # crypto_service.encrypt_token() 으로 암호화 저장
    calendar_id = Column(String(200), nullable=False)
    sync_direction = Column(String(20), default="cs_to_google")  # cs_to_google / google_to_cs / bidirectional
    is_active = Column(Boolean, default=True)
    last_synced_at = Column(DateTime, nullable=True)

    user = relationship("User", backref="calendar_syncs")
    events = relationship("CalendarEvent", back_populates="calendar_sync", cascade="all, delete-orphan")


class CalendarEvent(Base):
    """캘린더 이벤트 매핑 — Task ↔ 외부 캘린더 이벤트"""
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    calendar_sync_id = Column(Integer, ForeignKey("calendar_syncs.id", ondelete="CASCADE"), nullable=False)
    external_event_id = Column(String(200), nullable=False)
    synced_at = Column(DateTime, default=utc_now)

    task = relationship("Task", backref="calendar_events")
    calendar_sync = relationship("CalendarSync", back_populates="events")


# ══════════════════════════════════════════════════════════
# 19. 댓글 및 멘션  (변경: contract_id→project_id, task_id FK, document_id 추가)
# ══════════════════════════════════════════════════════════

class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comment_project_task", "project_id", "task_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    parent_id = Column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", backref="comments")
    project = relationship("Project", back_populates="comments")
    task = relationship("Task", back_populates="comments")
    document = relationship("Document", backref="comments")
    parent = relationship("Comment", remote_side="Comment.id", backref="replies")


class CommentRead(Base):
    """댓글 읽음 추적 (#7)"""
    __tablename__ = "comment_reads"
    __table_args__ = (
        UniqueConstraint("comment_id", "user_id", name="uq_comment_read"),
        Index("ix_comment_reads_comment", "comment_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    comment_id = Column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    read_at = Column(DateTime, default=utc_now)


# ══════════════════════════════════════════════════════════
# 20. 알림  (기존 유지 — 유형 확장)
# ══════════════════════════════════════════════════════════

class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notification_user_read", "user_id", "is_read"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)
    # v1: comment, mention, assign, status_change, team_invite, deadline
    # v2: feedback_received, revision_requested, report_ready,
    #     payment_due, payment_overdue, auto_confirmed, recurring_task, calendar_sync_error
    title = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    link = Column(String, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", backref="notifications")


# ══════════════════════════════════════════════════════════
# 21. 활동 로그  (변경: contract_id→project_id, client_id 추가)
# ══════════════════════════════════════════════════════════

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False)
    # create, update, delete, assign, status_change, comment,
    # confirm, send, receive, generate, auto_confirm
    target_type = Column(String, nullable=False)
    # project, task, client, document, completion_report, feedback, ai_report, payment, member
    target_name = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", backref="activity_logs")


# ══════════════════════════════════════════════════════════
#  RBAC 권한 매트릭스  (v2 확장)
# ══════════════════════════════════════════════════════════

TEAM_PERMISSIONS = {
    "owner": {
        "team.update", "team.delete", "team.invite", "team.remove_member", "team.change_role",
        "client.create", "client.update", "client.delete",
        "project.create", "project.update", "project.delete",
        "task.create", "task.update", "task.delete", "task.assign",
        "document.create", "document.update", "document.delete",
        "report.create", "report.send",
        "payment.create", "payment.update",
        "template.create", "template.delete",
        "comment.create", "comment.delete_any",
        # 4차 개발
        "board.create", "board.post", "board.pin", "board.delete_any",
        "invite.create", "invite.cancel",
        "attendance.admin", "attendance.policy",
    },
    "admin": {
        "team.update", "team.invite", "team.remove_member",
        "client.create", "client.update", "client.delete",
        "project.create", "project.update", "project.delete",
        "task.create", "task.update", "task.delete", "task.assign",
        "document.create", "document.update", "document.delete",
        "report.create", "report.send",
        "payment.create", "payment.update",
        "template.create", "template.delete",
        "comment.create", "comment.delete_any",
        # 4차 개발
        "board.create", "board.post", "board.pin", "board.delete_any",
        "invite.create", "invite.cancel",
        "attendance.admin",
    },
    "member": {
        "client.create", "client.update",
        "project.create",
        "task.create", "task.update", "task.assign",
        "document.create", "document.update",
        "report.create", "report.send",
        "comment.create",
        # 4차 개발
        "board.post",
    },
    "viewer": {
        "comment.create",
    },
}


# ══════════════════════════════════════════════════════════
#  DB 초기화 및 v1→v2 마이그레이션
# ══════════════════════════════════════════════════════════

async def init_db():
    from sqlalchemy import text, inspect as sa_inspect

    async with engine.begin() as conn:
        # 1) contracts → projects 테이블 리네임 (v1→v2 마이그레이션)
        def _check_tables(sync_conn):
            insp = sa_inspect(sync_conn)
            return insp.get_table_names()

        table_names = await conn.run_sync(_check_tables)

        if "contracts" in table_names and "projects" not in table_names:
            await conn.execute(text("ALTER TABLE contracts RENAME TO projects"))
            # contract_name → project_name 컬럼 추가 (데이터 복사)
            try:
                await conn.execute(text(
                    "ALTER TABLE projects ADD COLUMN project_name VARCHAR(500)"
                ))
                await conn.execute(text(
                    "UPDATE projects SET project_name = contract_name WHERE project_name IS NULL"
                ))
            except Exception:
                pass

        # 2) 모든 테이블 생성 (없는 것만 생성)
        await conn.run_sync(Base.metadata.create_all)

        # 3) 기존 테이블에 신규 컬럼 추가 (이미 있으면 무시)
        new_columns = [
            # projects (v1 contracts에서 확장)
            ("projects", "client_id", "INTEGER"),
            ("projects", "project_name", "VARCHAR(500)"),
            ("projects", "project_type", "VARCHAR(20) DEFAULT 'outsourcing'"),
            ("projects", "status", "VARCHAR(20) DEFAULT 'planning'"),
            ("projects", "description", "TEXT"),
            ("projects", "start_date", "VARCHAR"),
            ("projects", "end_date", "VARCHAR"),
            ("projects", "report_opt_in", "BOOLEAN DEFAULT 0"),
            ("projects", "report_frequency", "VARCHAR(10)"),
            # projects — v1 호환 (contracts에 이미 있을 수 있는 컬럼)
            ("projects", "company_name", "VARCHAR"),
            ("projects", "contractor", "VARCHAR"),
            ("projects", "contract_date", "VARCHAR"),
            ("projects", "contract_amount", "VARCHAR"),
            ("projects", "payment_method", "VARCHAR"),
            ("projects", "payment_due_date", "VARCHAR"),
            ("projects", "milestones", "JSON"),
            ("projects", "raw_text", "TEXT"),
            ("projects", "team_id", "INTEGER"),
            # comments 확장
            ("comments", "project_id", "INTEGER"),
            ("comments", "document_id", "INTEGER"),
            # comments — 2차 개발 (#6 스레드)
            ("comments", "parent_id", "INTEGER REFERENCES comments(id) ON DELETE CASCADE"),
            # activity_logs 확장
            ("activity_logs", "project_id", "INTEGER"),
            ("activity_logs", "client_id", "INTEGER"),
            # 3차 개발 — User 확장
            ("users", "user_type", "VARCHAR(20) DEFAULT 'human'"),
            # 3차 개발 — Figma 연동
            ("projects", "figma_urls", "JSON"),
            # 5차 개발 — 캘린더 동기화 방향
            ("calendar_syncs", "sync_direction", "VARCHAR(20) DEFAULT 'cs_to_google'"),
            # 5차 개발 — 업무 출처
            ("tasks", "source", "VARCHAR(30)"),
        ]
        for tbl, col_name, col_type in new_columns:
            try:
                await conn.execute(text(
                    f"ALTER TABLE {tbl} ADD COLUMN {col_name} {col_type}"
                ))
            except Exception:
                pass

        # 4) v1 데이터 마이그레이션: contract_id → project_id 복사 후 contract_id 제거
        migration_copies = [
            ("comments", "project_id", "contract_id"),
            ("activity_logs", "project_id", "contract_id"),
        ]
        for tbl, new_col, old_col in migration_copies:
            try:
                await conn.execute(text(
                    f"UPDATE {tbl} SET {new_col} = {old_col} WHERE {new_col} IS NULL AND {old_col} IS NOT NULL"
                ))
            except Exception:
                pass

        # 4-1) comments/activity_logs 테이블 재구축 (contract_id 제거, task_id 타입 변경)
        # SQLite DROP COLUMN이 FK 제약으로 실패하므로 테이블 재생성 방식
        await conn.execute(text("PRAGMA foreign_keys=OFF"))

        # comments 재구축
        try:
            existing = await conn.execute(text("PRAGMA table_info(comments)"))
            col_names = [r[1] for r in existing.fetchall()]
            if "contract_id" in col_names:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS comments_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                        task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                        document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        content TEXT NOT NULL,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                """))
                await conn.execute(text("""
                    INSERT OR IGNORE INTO comments_v2 (id, project_id, task_id, user_id, content, created_at, updated_at, document_id)
                    SELECT id, COALESCE(project_id, contract_id), NULL, user_id, content, created_at, updated_at, document_id
                    FROM comments
                """))
                await conn.execute(text("DROP TABLE comments"))
                await conn.execute(text("ALTER TABLE comments_v2 RENAME TO comments"))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_comment_project_task ON comments (project_id, task_id)"
                ))
        except Exception:
            pass

        # activity_logs 재구축
        try:
            existing = await conn.execute(text("PRAGMA table_info(activity_logs)"))
            col_names = [r[1] for r in existing.fetchall()]
            if "contract_id" in col_names:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS activity_logs_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
                        team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        action VARCHAR NOT NULL,
                        target_type VARCHAR NOT NULL,
                        target_name VARCHAR,
                        detail TEXT,
                        created_at DATETIME,
                        client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL
                    )
                """))
                await conn.execute(text("""
                    INSERT OR IGNORE INTO activity_logs_v2 (id, project_id, team_id, user_id, action, target_type, target_name, detail, created_at, client_id)
                    SELECT id, COALESCE(project_id, contract_id), team_id, user_id, action, target_type, target_name, detail, created_at, client_id
                    FROM activity_logs
                """))
                await conn.execute(text("DROP TABLE activity_logs"))
                await conn.execute(text("ALTER TABLE activity_logs_v2 RENAME TO activity_logs"))
        except Exception:
            pass

        await conn.execute(text("PRAGMA foreign_keys=ON"))

        # project_name이 비어있으면 contract_name에서 복사
        try:
            await conn.execute(text(
                "UPDATE projects SET project_name = contract_name "
                "WHERE project_name IS NULL AND contract_name IS NOT NULL"
            ))
        except Exception:
            pass

        # contract_name이 비어있으면 project_name에서 복사 (v2 → v1 호환)
        try:
            await conn.execute(text(
                "UPDATE projects SET contract_name = project_name "
                "WHERE contract_name IS NULL AND project_name IS NOT NULL"
            ))
        except Exception:
            pass

        # 5) 인덱스 추가
        new_indexes = [
            "CREATE INDEX IF NOT EXISTS ix_comment_project_task ON comments (project_id, task_id)",
            "CREATE INDEX IF NOT EXISTS ix_notification_user_read ON notifications (user_id, is_read)",
            "CREATE INDEX IF NOT EXISTS ix_client_team_user ON clients (team_id, user_id)",
            "CREATE INDEX IF NOT EXISTS ix_task_project ON tasks (project_id)",
            "CREATE INDEX IF NOT EXISTS ix_task_assignee ON tasks (assignee_id)",
            "CREATE INDEX IF NOT EXISTS ix_task_status ON tasks (status)",
            "CREATE INDEX IF NOT EXISTS ix_task_due_date ON tasks (due_date)",
            "CREATE INDEX IF NOT EXISTS ix_task_team_status ON tasks (team_id, status)",
            "CREATE INDEX IF NOT EXISTS ix_document_project_type ON documents (project_id, document_type)",
            "CREATE INDEX IF NOT EXISTS ix_payment_project_status ON payment_schedules (project_id, status)",
            "CREATE INDEX IF NOT EXISTS ix_payment_due_status ON payment_schedules (due_date, status)",
            "CREATE INDEX IF NOT EXISTS ix_completion_report_task ON completion_reports (task_id)",
            "CREATE INDEX IF NOT EXISTS ix_completion_report_token ON completion_reports (feedback_token)",
            "CREATE INDEX IF NOT EXISTS ix_portal_token ON portal_tokens (token)",
            "CREATE INDEX IF NOT EXISTS ix_comment_parent ON comments (parent_id)",
            "CREATE INDEX IF NOT EXISTS ix_comment_reads_comment ON comment_reads (comment_id)",
            # 3차 개발
            "CREATE INDEX IF NOT EXISTS ix_chat_message_session ON chat_messages (chat_session_id)",
            "CREATE INDEX IF NOT EXISTS ix_chat_session_user ON chat_sessions (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_feedback_request_project ON feedback_requests (project_id)",
            "CREATE INDEX IF NOT EXISTS ix_feedback_request_token ON feedback_requests (feedback_token)",
            "CREATE INDEX IF NOT EXISTS ix_feedback_request_status ON feedback_requests (status)",
            # 4차 개발
            "CREATE INDEX IF NOT EXISTS ix_board_post_board ON board_posts (board_id)",
            "CREATE INDEX IF NOT EXISTS ix_board_post_author ON board_posts (author_id)",
            "CREATE INDEX IF NOT EXISTS ix_board_comment_post ON board_comments (post_id)",
            "CREATE INDEX IF NOT EXISTS ix_pending_invite_token ON pending_invites (token)",
            "CREATE INDEX IF NOT EXISTS ix_pending_invite_email ON pending_invites (email)",
            "CREATE INDEX IF NOT EXISTS ix_user_task_priority_user ON user_task_priorities (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_chatroom_member_user ON chat_room_members (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_room_message_room ON room_messages (room_id)",
            "CREATE INDEX IF NOT EXISTS ix_room_message_created ON room_messages (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_attendance_team_date ON attendances (team_id, date)",
            "CREATE INDEX IF NOT EXISTS ix_attendance_user_date ON attendances (user_id, date)",
        ]
        for idx_sql in new_indexes:
            try:
                await conn.execute(text(idx_sql))
            except Exception:
                pass

        # TeamMember 중복 방지
        try:
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_team_user ON team_members (team_id, user_id)"
            ))
        except Exception:
            pass

        # 3차 개발: AI 에이전트 시스템 사용자 생성 (S1-2)
        try:
            existing = await conn.execute(text(
                "SELECT id FROM users WHERE email = 'system@contract-sync.local'"
            ))
            if not existing.fetchone():
                await conn.execute(text(
                    "INSERT INTO users (email, name, is_verified, is_active, auth_provider, user_type) "
                    "VALUES ('system@contract-sync.local', 'CS 어시스턴트', 1, 1, 'system', 'ai_agent')"
                ))
        except Exception:
            pass


async def get_db():
    async with async_session() as session:
        yield session

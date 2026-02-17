from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> datetime:
    """SQLite 호환 naive UTC 현재 시각 반환"""
    return datetime.now(timezone.utc).replace(tzinfo=None)

# Railway에서는 /app 디렉토리 사용
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "contract_sync.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    auth_provider = Column(String, default="email")  # email or google
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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", backref="sessions")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now)

    creator = relationship("User", backref="created_teams")
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, default="member")  # owner, admin, member
    joined_at = Column(DateTime, default=utc_now)

    team = relationship("Team", back_populates="members")
    user = relationship("User", backref="team_memberships")


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)
    contract_name = Column(String, nullable=False)
    file_name = Column(String, nullable=True)
    company_name = Column(String, nullable=True)  # 기업명
    contractor = Column(String, nullable=True)  # 수급자
    client = Column(String, nullable=True)  # 발주처
    contract_date = Column(String, nullable=True)  # 계약일
    contract_start_date = Column(String, nullable=True)  # 착수일
    contract_end_date = Column(String, nullable=True)  # 완수일
    total_duration_days = Column(Integer, nullable=True)
    contract_amount = Column(String, nullable=True)  # 계약 금액
    payment_method = Column(String, nullable=True)  # 계약금 지급 방식
    payment_due_date = Column(String, nullable=True)  # 입금예정일
    schedules = Column(JSON, nullable=True)  # 일정 목록
    tasks = Column(JSON, nullable=True)  # 업무 목록
    milestones = Column(JSON, nullable=True)  # 마일스톤
    raw_text = Column(Text, nullable=True)  # 원본 텍스트 (워드 저장용)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", backref="contracts")
    team = relationship("Team", backref="contracts")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String, nullable=True)  # null이면 계약 전체 댓글
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", backref="comments")
    contract = relationship("Contract", backref="comments")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)  # comment, assign, status_change, mention, deadline
    title = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    link = Column(String, nullable=True)  # 관련 페이지 링크 정보 (JSON)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", backref="notifications")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)  # create, update, delete, assign, status_change, comment 등
    target_type = Column(String, nullable=False)  # contract, task, team, member
    target_name = Column(String, nullable=True)
    detail = Column(Text, nullable=True)  # 변경 상세 (JSON 또는 텍스트)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", backref="activity_logs")


# 팀 역할별 권한 정의
TEAM_PERMISSIONS = {
    "owner": {
        "team.update", "team.delete", "team.invite", "team.remove_member", "team.change_role",
        "contract.create", "contract.update", "contract.delete",
        "task.create", "task.update", "task.delete", "task.assign",
        "comment.create", "comment.delete_any",
    },
    "admin": {
        "team.update", "team.invite", "team.remove_member",
        "contract.create", "contract.update", "contract.delete",
        "task.create", "task.update", "task.delete", "task.assign",
        "comment.create", "comment.delete_any",
    },
    "member": {
        "contract.create",
        "task.create", "task.update", "task.assign",
        "comment.create",
    },
    "viewer": {
        "comment.create",
    },
}


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # 기존 테이블에 새 컬럼 추가 (이미 있으면 무시)
        new_columns = [
            ("contracts", "company_name", "VARCHAR"),
            ("contracts", "contractor", "VARCHAR"),
            ("contracts", "client", "VARCHAR"),
            ("contracts", "contract_date", "VARCHAR"),
            ("contracts", "contract_amount", "VARCHAR"),
            ("contracts", "payment_method", "VARCHAR"),
            ("contracts", "payment_due_date", "VARCHAR"),
            ("contracts", "milestones", "JSON"),
            ("contracts", "raw_text", "TEXT"),
            ("contracts", "team_id", "INTEGER"),
        ]
        for table, col_name, col_type in new_columns:
            try:
                await conn.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"
                    )
                )
            except Exception:
                pass  # 이미 존재하는 컬럼


async def get_db():
    async with async_session() as session:
        yield session

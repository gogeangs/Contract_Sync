from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from datetime import datetime
from pathlib import Path
import os

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
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    auth_provider = Column(String, default="email")  # email or google
    created_at = Column(DateTime, default=datetime.utcnow)


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="contracts")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # 기존 테이블에 새 컬럼 추가 (이미 있으면 무시)
        new_columns = [
            ("company_name", "VARCHAR"),
            ("contract_date", "VARCHAR"),
            ("contract_amount", "VARCHAR"),
            ("payment_method", "VARCHAR"),
            ("payment_due_date", "VARCHAR"),
        ]
        for col_name, col_type in new_columns:
            try:
                await conn.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE contracts ADD COLUMN {col_name} {col_type}"
                    )
                )
            except Exception:
                pass  # 이미 존재하는 컬럼


async def get_db():
    async with async_session() as session:
        yield session

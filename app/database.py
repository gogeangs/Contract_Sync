from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from datetime import datetime

DATABASE_URL = "sqlite+aiosqlite:///./contract_sync.db"

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
    contractor = Column(String, nullable=True)  # 계약자
    client = Column(String, nullable=True)  # 발주처
    contract_start_date = Column(String, nullable=True)
    contract_end_date = Column(String, nullable=True)
    total_duration_days = Column(Integer, nullable=True)
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


async def get_db():
    async with async_session() as session:
        yield session

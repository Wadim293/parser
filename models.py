from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, ForeignKey, UniqueConstraint, func
from config import POSTGRES_URI

Base = declarative_base()
engine = create_async_engine(POSTGRES_URI, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True)
    full_name = Column(String(255))
    username = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_chat_link = Column(String(1000), nullable=True)
    parse_nft_all = Column(Boolean, default=True)
    parse_nft_premium = Column(Boolean, default=False)
    parse_exclude_admins = Column(Boolean, default=True)

    accounts = relationship("Account", back_populates="user")
    spam_tasks = relationship("SpamTask", back_populates="user")


class Account(Base):
    __tablename__ = 'accounts'
    __table_args__ = (UniqueConstraint('phone_number', 'user_id', name='_phone_user_uc'),)

    id = Column(Integer, primary_key=True)
    phone_number = Column(String(32))
    session_name = Column(String(1000))
    user_id = Column(Integer, ForeignKey('users.id'))
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="accounts")
    spam_tasks = relationship("SpamTask", back_populates="account")


class ChatLink(Base):
    __tablename__ = 'chat_links'

    id = Column(Integer, primary_key=True)
    url = Column(String(1000), unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SpamTask(Base):
    __tablename__ = 'spam_tasks'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    account_id = Column(Integer, ForeignKey('accounts.id'))
    file_name = Column(String(255), nullable=True)
    message_file = Column(String(255), nullable=True)
    message_limit = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sent_success = Column(Integer, default=0)
    sent_errors = Column(Integer, default=0)
    is_running = Column(Boolean, default=False)

    user = relationship("User", back_populates="spam_tasks")
    account = relationship("Account", back_populates="spam_tasks")

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
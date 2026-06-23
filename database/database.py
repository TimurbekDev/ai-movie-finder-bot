from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import DATABASE_URL
from database.models import Base

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for index in Base.metadata.tables["search_history"].indexes:
            await conn.run_sync(lambda c, idx=index: idx.create(c, checkfirst=True))


@asynccontextmanager
async def get_session():
    async with async_session() as session:
        yield session

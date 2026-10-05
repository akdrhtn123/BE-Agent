from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, TypeDecorator, inspect
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from be_agent.db.models import Base


def create_engine(database_url: str) -> AsyncEngine:
    if database_url.startswith("sqlite"):
        path = database_url.split("///", 1)[-1]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return create_async_engine(database_url)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


# Alembic 도입 전(create_all 방식)에 만든 DB 는 이 버전과 같은 구조라고 보고 기록만 남긴다
BASELINE_REVISION = "0001"
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """같은 DB 에 LangGraph 체크포인터 테이블(checkpoints 등)이 있어도 모델에 없는 테이블은 건드리지 않는다."""
    if type_ == "table":
        return name in Base.metadata.tables
    return True


def render_item(type_, obj, autogen_context):
    """UTCDateTime 같은 TypeDecorator 는 파이썬 쪽 변환일 뿐이라 마이그레이션에는 실제 DB 타입(impl)으로 적는다.

    그래야 마이그레이션 파일이 앱 코드를 import 하지 않는다.
    """
    if type_ == "type" and isinstance(obj, TypeDecorator):
        return f"sa.{obj.impl!r}"
    return False


def _alembic_config(conn: Connection) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["connection"] = conn
    return config


def _migrate(conn: Connection) -> None:
    config = _alembic_config(conn)
    tables = set(inspect(conn).get_table_names())
    if "alembic_version" not in tables and "users" in tables:
        command.stamp(config, BASELINE_REVISION)
    command.upgrade(config, "head")


async def init_db(engine: AsyncEngine) -> None:
    """DB 를 최신 마이그레이션까지 올린다 (migrations/versions)."""
    async with engine.begin() as conn:
        await conn.run_sync(_migrate)

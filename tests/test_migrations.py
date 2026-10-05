from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, inspect, text

from be_agent.db.models import Base
from be_agent.db.session import MIGRATIONS_DIR, create_engine, include_object, init_db


def _head() -> str:
    head = ScriptDirectory(str(MIGRATIONS_DIR)).get_current_head()
    assert head is not None
    return head


def _current(conn: Connection) -> str | None:
    return MigrationContext.configure(conn).get_current_revision()


def _diff(conn: Connection) -> list:
    context = MigrationContext.configure(conn, opts={"include_object": include_object})
    return compare_metadata(context, Base.metadata)


async def test_migrations_match_models(tmp_path: Path) -> None:
    """모델을 고치고 마이그레이션을 안 만들면 여기서 실패한다: uv run alembic revision --autogenerate -m '...'"""
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path}/app.db")
    await init_db(engine)
    async with engine.connect() as conn:
        assert await conn.run_sync(_current) == _head()
        assert await conn.run_sync(_diff) == []
    await engine.dispose()


async def test_legacy_db_is_stamped_then_upgraded(tmp_path: Path) -> None:
    """Alembic 도입 전 create_all 로 만든 DB 는 데이터를 지키며 baseline 으로 기록된 뒤 최신까지 올라간다."""
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path}/app.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, created_at) "
                "VALUES ('u1', 'old@example.com', 'x', CURRENT_TIMESTAMP)"
            )
        )

    await init_db(engine)

    async with engine.connect() as conn:
        assert await conn.run_sync(_current) == _head()
        assert (await conn.execute(text("SELECT email FROM users"))).scalar_one() == "old@example.com"
    await engine.dispose()


async def test_unknown_tables_are_left_alone(tmp_path: Path) -> None:
    """같은 DB 의 체크포인터 테이블 같은 모델 밖 테이블은 비교·삭제 대상이 아니다."""
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path}/app.db")
    await init_db(engine)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE checkpoints (thread_id TEXT)"))
        assert await conn.run_sync(_diff) == []
        assert "checkpoints" in await conn.run_sync(lambda c: inspect(c).get_table_names())
    await engine.dispose()

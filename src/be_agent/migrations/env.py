"""Alembic 실행 환경.

- CLI(`uv run alembic ...`): 접속 주소는 Settings(DATABASE_URL)에서 읽는다. alembic.ini 에 두지 않는다.
- 서버 시작(`db.session.init_db`): 이미 열린 연결을 config.attributes["connection"] 으로 넘겨받아 그 위에서 돌린다.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from be_agent.core.config import get_settings
from be_agent.db.models import Base
from be_agent.db.session import create_engine, include_object, render_item

config = context.config
target_metadata = Base.metadata

# 서버 안에서 돌 때는 uvicorn 로깅을 덮어쓰지 않도록 CLI 일 때만 ini 로깅 설정을 쓴다
if config.config_file_name is not None and "connection" not in config.attributes:
    fileConfig(config.config_file_name)


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        render_item=render_item,
        render_as_batch=True,  # SQLite 는 ALTER 가 제한적이라 테이블 복사 방식으로 변경한다
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("오프라인(--sql) 모드는 지원하지 않는다")

connection = config.attributes.get("connection")
if connection is not None:
    do_run_migrations(connection)
else:
    asyncio.run(run_async_migrations())

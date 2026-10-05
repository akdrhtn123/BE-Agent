"""DB 를 최신 마이그레이션까지 올리고 끝난다. 서버와 따로 배포 전에 한 번만 돌릴 때 쓴다 (쿠버네티스 Job 등).

    python -m be_agent.db.migrate           # 최신까지 올린다
    python -m be_agent.db.migrate --check   # 최신이면 0, 아니면(접속 실패 포함) 1. 서버가 Job 을 기다릴 때

접속 주소는 Settings(DATABASE_URL)에서 읽는다. 서버 시작 때와 같은 init_db 를 쓰므로 결과도 같다.
"""

import asyncio
import logging
import sys

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection

from be_agent.core.config import get_settings
from be_agent.db.session import MIGRATIONS_DIR, create_engine, init_db


async def migrate(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        await init_db(engine)
    finally:
        await engine.dispose()


def _at_head(conn: Connection) -> bool:
    head = ScriptDirectory(str(MIGRATIONS_DIR)).get_current_head()
    return MigrationContext.configure(conn).get_current_revision() == head


async def is_up_to_date(database_url: str) -> bool:
    engine = create_engine(database_url)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(_at_head)
    finally:
        await engine.dispose()


def main() -> None:
    url = get_settings().database_url
    if "--check" in sys.argv[1:]:
        try:
            ok = asyncio.run(is_up_to_date(url))
        except Exception as e:  # noqa: BLE001 — DB 가 아직 안 떴을 때도 "아직 아님"으로 끝낸다
            print(f"DB 확인 실패: {e.__class__.__name__}", file=sys.stderr)
            ok = False
        if not ok:
            print("DB 마이그레이션이 아직 최신이 아닙니다", file=sys.stderr)
        sys.exit(0 if ok else 1)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    asyncio.run(migrate(url))


if __name__ == "__main__":
    main()

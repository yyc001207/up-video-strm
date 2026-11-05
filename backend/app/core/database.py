"""SQLite 异步数据库：启动时自动建表 + 种子数据（本地部署，无需 Alembic 迁移）。"""

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.settings import settings

# 确保 SQLite 文件所在目录存在
_db_path = Path(settings.sqlite_path)
_db_path.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{settings.sqlite_path}"
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

logger = logging.getLogger("up-video-strm")

# 功能已移除、但旧库仍残留的列：旧库中部分列是 NOT NULL（如 strip_series），
# 新代码不再写入会让插入失败，因此启动时清理旧列，保证升级用户可继续新增记录。
_OBSOLETE_COLUMNS: dict[str, tuple[str, ...]] = {
    "open_list_execution": ("strip_series", "server_name"),
    "open_list_config": ("log_to_db",),
    "open_list_server": ("name",),
}

# SQLite 3.35+ 才支持 ALTER TABLE ... DROP COLUMN。
_SQLITE_DROP_COLUMN_MIN_VERSION = (3, 35, 0)


def obsolete_column_statements(existing_columns: dict[str, set[str]]) -> list[str]:
    """按现有列集合生成清理旧列的 ALTER 语句（纯函数，便于单元测试）。"""
    return [
        f"ALTER TABLE {table} DROP COLUMN {column}"
        for table, columns in _OBSOLETE_COLUMNS.items()
        for column in columns
        if column in existing_columns.get(table, set())
    ]


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def _ensure_config_columns() -> None:
    """轻量列级迁移：create_all 不会为已存在的表补列，这里用 PRAGMA 检查后 ALTER 补齐新字段。

    SQLite 支持 ADD COLUMN，追加可空列即可；新库由 create_all 直接建好，此函数自动跳过。
    """
    new_columns = {
        "process_path_prefix": "VARCHAR(128)",
        "output_dir_prefix": "VARCHAR(128)",
        "output_root": "VARCHAR(512)",
    }
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(open_list_config)"))
        existing = {row[1] for row in result}
        for column, ddl in new_columns.items():
            if column not in existing:
                await conn.execute(text(f"ALTER TABLE open_list_config ADD COLUMN {column} {ddl}"))


async def _ensure_execution_columns() -> None:
    """执行记录表补齐目录执行快照列（create_all 对已存在表不生效，需 ALTER）。"""
    new_columns = {
        "process_path": "VARCHAR(512)",
        "output_dir": "VARCHAR(512)",
    }
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(open_list_execution)"))
        existing = {row[1] for row in result}
        for column, ddl in new_columns.items():
            if column not in existing:
                await conn.execute(text(f"ALTER TABLE open_list_execution ADD COLUMN {column} {ddl}"))


async def _ensure_task_columns() -> None:
    """任务表补齐服务器关联列（强关联服务器）。"""
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(open_list_task)"))
        existing = {row[1] for row in result}
        if "server_id" not in existing:
            await conn.execute(text("ALTER TABLE open_list_task ADD COLUMN server_id INTEGER"))


async def _drop_obsolete_columns() -> None:
    """清理旧库中已废弃的列（功能已移除但仍残留）。

    旧库的 ``open_list_execution.strip_series``、``open_list_config.log_to_db``
    等列带 NOT NULL 约束且新代码不再写入，不清理会导致新增执行/配置记录时报
    ``NOT NULL constraint failed``。新库由 create_all 直接建出干净结构，此函数自动跳过。
    """
    async with engine.begin() as conn:
        version_text = (await conn.execute(text("select sqlite_version()"))).scalar() or "0.0.0"
        version = tuple(int(part) for part in version_text.split(".")[:3])
        if version < _SQLITE_DROP_COLUMN_MIN_VERSION:
            logger.warning(
                "SQLite %s 不支持 DROP COLUMN，跳过旧列清理（升级用户可能无法新增记录）",
                version_text,
            )
            return
        existing_columns: dict[str, set[str]] = {}
        for table in _OBSOLETE_COLUMNS:
            rows = await conn.execute(text(f"PRAGMA table_info({table})"))
            existing_columns[table] = {row[1] for row in rows}
        statements = obsolete_column_statements(existing_columns)
        for statement in statements:
            await conn.execute(text(statement))
        if statements:
            logger.info("已清理旧库废弃列：%s", len(statements))


async def _bind_orphan_tasks_to_default_server() -> None:
    """迁移：旧任务（server_id 为空）绑定到第一个启用服务器（幂等）。"""
    from sqlalchemy import select

    from app.core.models import OpenListServer, OpenListTask

    async with AsyncSessionLocal() as db:
        server = await db.scalar(
            select(OpenListServer)
            .where(OpenListServer.is_deleted == False)  # noqa: E712
            .order_by(OpenListServer.id)
            .limit(1)
        )
        if server is None:
            return
        result = await db.execute(
            select(OpenListTask).where(
                OpenListTask.server_id.is_(None),
                OpenListTask.is_deleted == False,  # noqa: E712
            )
        )
        tasks = list(result.scalars())
        if not tasks:
            return
        for task in tasks:
            task.server_id = server.id
        await db.commit()


async def init_db() -> None:
    """建表、轻量迁移并写入默认 OpenList 全局配置（幂等）。"""
    from app.core import models  # noqa: F401   # 注册全部模型到 Base
    from app.business.openlist.service import seed_default_openlist_config

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_config_columns()
    await _ensure_execution_columns()
    await _ensure_task_columns()
    await _drop_obsolete_columns()
    async with AsyncSessionLocal() as session:
        await seed_default_openlist_config(session)
    await _bind_orphan_tasks_to_default_server()

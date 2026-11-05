#!/usr/bin/env python3
"""修复旧版数据库的 schema 问题（仅老库升级时需要）。

适用场景：
    数据库是用旧版源码建的 —— users.uid 上只有部分唯一索引
    （WHERE is_deleted = 0），没有全表 UNIQUE 约束。
    PostgreSQL 要求外键引用的列上必须有真正的 UNIQUE 约束，
    因此 agent_envs / user_config 建表会失败，并导致整批 create_all 回滚。

    当前版本源码已在 models_business.py 里加了
    UniqueConstraint("uid", name="users_uid_key")，全新部署不需要跑本脚本。

用法（容器内执行）：
    docker compose run --rm --no-deps --entrypoint python \
      xiaozhi-api /app/scripts/fix_schema.py

脚本做了什么：
    1. users 表存在但没有 uid 的 UNIQUE 约束 → 补一个 users_uid_key
    2. 补约束前，把重复的软删除记录 uid 改成 uid_deleted_<id>（不删数据）
    3. 跑一次 create_all，补齐所有缺失的表
"""

import asyncio
import os
import sys
from pathlib import Path

_here = Path(__file__).resolve()
for _cand in ("/app/package", str(_here.parent.parent / "backend" / "package")):
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from xiaozhi.storage.postgres.models_business import Base as BusinessBase  # noqa: E402
from xiaozhi.storage.postgres.models_knowledge import Base as KnowledgeBase  # noqa: E402

HAS_UID_UNIQUE = text(
    """
    SELECT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'users'
          AND c.contype = 'u'
          AND (
              SELECT array_agg(a.attname ORDER BY a.attname)
              FROM unnest(c.conkey) AS k
              JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k
          ) = ARRAY['uid']
    )
    """
)

DEDUP_SOFT_DELETED = text(
    """
    UPDATE users u
    SET uid = u.uid || '_deleted_' || u.id
    WHERE u.id IN (
        SELECT id FROM (
            SELECT id,
                   row_number() OVER (PARTITION BY uid ORDER BY is_deleted ASC, id ASC) AS rn
            FROM users
        ) AS t
        WHERE t.rn > 1
    )
    """
)


async def main() -> int:
    db_url = os.environ.get("POSTGRES_URL", "").strip()
    if not db_url:
        print("[ERROR] 环境变量 POSTGRES_URL 未设置，请在容器内执行本脚本")
        return 1

    engine = create_async_engine(db_url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            users_exists = await conn.scalar(text("SELECT to_regclass('public.users') IS NOT NULL"))

            if users_exists:
                has_constraint = await conn.scalar(HAS_UID_UNIQUE)
                if has_constraint:
                    print("[1/3] users_uid_key 已存在，跳过")
                else:
                    result = await conn.execute(DEDUP_SOFT_DELETED)
                    print(f"[1/3] 已为重复软删除记录改写 uid：{result.rowcount} 行")
                    await conn.execute(
                        text("ALTER TABLE users ADD CONSTRAINT users_uid_key UNIQUE (uid)")
                    )
                    print("[1/3] 已补 users_uid_key 唯一约束")
            else:
                print("[1/3] users 表不存在，属于全新库，无需修复")

            await conn.run_sync(BusinessBase.metadata.create_all)
            print("[2/3] 业务表已补齐")

            await conn.run_sync(KnowledgeBase.metadata.create_all)
            print("[3/3] 知识库表已补齐")
    finally:
        await engine.dispose()

    print()
    print("完成。若之前漏建过表，现在可以重启 api：docker compose restart xiaozhi-api")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

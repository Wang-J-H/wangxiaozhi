#!/usr/bin/env python3
"""创建超级管理员账号。

系统没有「首次启动自动建管理员」机制，users 表建好后是空的，
必须手动跑一次本脚本，否则登录一律返回 401。

用法（容器内执行）：
    docker compose run --rm --no-deps --entrypoint python \
      xiaozhi-api /app/scripts/seed_admin.py

可覆盖的环境变量：
    SEED_ADMIN_UID       登录标识，默认 admin
    SEED_ADMIN_NAME      显示名称，默认 管理员
    SEED_ADMIN_PASSWORD  密码，默认 admin123
    SEED_ADMIN_DEPT      所属部门，默认 研发部
    SEED_ADMIN_FORCE     设为 1 时，若账号已存在则重置密码
"""

import asyncio
import os
import sys
from pathlib import Path

# 兼容两种运行方式：容器内（PYTHONPATH=/app/package）和宿主机直接跑
_here = Path(__file__).resolve()
for _cand in ("/app/package", str(_here.parent.parent / "backend" / "package")):
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from xiaozhi.storage.postgres.models_business import (  # noqa: E402
    Base as BusinessBase,
    Department,
    User,
)
from xiaozhi.utils.auth_utils import AuthUtils  # noqa: E402


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


async def main() -> int:
    db_url = os.environ.get("POSTGRES_URL", "").strip()
    if not db_url:
        print("[ERROR] 环境变量 POSTGRES_URL 未设置，请在容器内执行本脚本")
        return 1

    uid = _env("SEED_ADMIN_UID", "admin")
    name = _env("SEED_ADMIN_NAME", "管理员")
    password = _env("SEED_ADMIN_PASSWORD", "admin123")
    dept_name = _env("SEED_ADMIN_DEPT", "研发部")
    force = _env("SEED_ADMIN_FORCE", "") in {"1", "true", "yes", "TRUE", "YES"}

    engine = create_async_engine(db_url, pool_pre_ping=True)
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        # 幂等建表：表已存在时不做任何改动
        async with engine.begin() as conn:
            await conn.run_sync(BusinessBase.metadata.create_all)
        print("[1/3] 数据表检查完成")

        async with Session() as session:
            dept = (
                await session.execute(select(Department).where(Department.name == dept_name))
            ).scalar_one_or_none()
            if dept is None:
                dept = Department(name=dept_name, description="系统初始化创建")
                session.add(dept)
                await session.flush()
                print(f"[2/3] 已创建部门：{dept_name}")
            else:
                print(f"[2/3] 部门已存在：{dept_name}")

            existing = (
                await session.execute(select(User).where(User.uid == uid))
            ).scalar_one_or_none()

            if existing is not None:
                if not force:
                    print(f"[3/3] 账号 {uid} 已存在，跳过（需重置密码请设 SEED_ADMIN_FORCE=1）")
                    return 0
                existing.username = name
                existing.password_hash = AuthUtils.hash_password(password)
                existing.role = "superadmin"
                existing.department_id = dept.id
                existing.is_deleted = 0
                existing.login_failed_count = 0
                existing.login_locked_until = None
                await session.commit()
                print(f"[3/3] 账号 {uid} 已存在，密码已重置")
            else:
                session.add(
                    User(
                        username=name,
                        uid=uid,
                        password_hash=AuthUtils.hash_password(password),
                        role="superadmin",
                        department_id=dept.id,
                        is_deleted=0,
                        login_failed_count=0,
                    )
                )
                await session.commit()
                print(f"[3/3] 已创建超级管理员：uid={uid} 名称={name} 部门={dept_name}")
    finally:
        await engine.dispose()

    print()
    print("完成。登录接口 POST /api/auth/token 的 username 字段填 uid，不是显示名称：")
    print(f"  uid  : {uid}")
    print(f"  密码 : {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from neuralops.db import engine


def test_fresh_upgrade_schema_parity_and_full_downgrade():
    name = "neuralops_migration_" + uuid4().hex[:12]
    administrator = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with administrator.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name}"))
    temporary = create_engine(engine.url.set(database=name))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    try:
        with temporary.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            command.check(config)
            assert connection.scalar(text("SELECT to_regclass('public.spans')")) == "spans"
            connection.commit()
            command.downgrade(config, "base")
            assert connection.scalar(text("SELECT to_regclass('public.spans')")) is None
            connection.commit()
            command.upgrade(config, "head")
            command.check(config)
    finally:
        temporary.dispose()
        with administrator.connect() as conn:
            conn.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))
        administrator.dispose()

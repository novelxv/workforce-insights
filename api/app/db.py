from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from app.config import get_settings

engine = create_engine(
    get_settings().sqlalchemy_url,
    pool_pre_ping=True,
    pool_size=4,
    max_overflow=4,
    connect_args={"prepare_threshold": None},
)


def get_conn() -> Iterator[Connection]:
    with engine.connect() as conn:
        yield conn

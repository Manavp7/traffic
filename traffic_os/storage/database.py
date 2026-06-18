"""SQL document/time-series store via SQLAlchemy Core.

Works on SQLite (dev) and PostgreSQL (prod) with the same code path. Entities are
stored in a single ``entities`` table with a JSON ``data`` payload plus a few
promoted, indexed columns (``ts``, ``segment_id``, ``status``) for fast queries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import orjson
from pydantic import BaseModel
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    func,
    select,
)
from sqlalchemy.engine import Engine

from traffic_os.common.logging import get_logger
from traffic_os.storage.ports import Database

log = get_logger("storage.db")

_metadata = MetaData()

entities = Table(
    "entities",
    _metadata,
    Column("collection", String(64), primary_key=True),
    Column("id", String(128), primary_key=True),
    Column("ts", DateTime(timezone=True), nullable=True, index=True),
    Column("segment_id", String(128), nullable=True, index=True),
    Column("status", String(32), nullable=True, index=True),
    Column("data", Text, nullable=False),
)

Index("ix_entities_coll_ts", entities.c.collection, entities.c.ts)
Index("ix_entities_coll_seg", entities.c.collection, entities.c.segment_id)


def _dump(obj: BaseModel) -> str:
    return orjson.dumps(obj.model_dump(mode="json")).decode()


def _promoted(obj: BaseModel) -> dict[str, Any]:
    # json mode renders enums as their values and datetimes as ISO strings
    d = obj.model_dump(mode="json")
    ts = d.get("ts") or d.get("ts_made")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return {
        "ts": ts,
        "segment_id": d.get("segment_id"),
        "status": str(d["status"]) if d.get("status") is not None else None,
    }


class SqlDatabase(Database):
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        _metadata.create_all(engine)

    @classmethod
    def sqlite(cls, path: str) -> SqlDatabase:
        engine = create_engine(f"sqlite:///{path}", future=True)
        return cls(engine)

    @classmethod
    def postgres(cls, dsn: str) -> SqlDatabase:
        engine = create_engine(dsn, future=True)
        return cls(engine)

    # -- writes ----------------------------------------------------------- #
    def upsert(self, collection: str, obj: BaseModel) -> None:
        self.upsert_many(collection, [obj])

    def upsert_many(self, collection: str, objs: list[BaseModel]) -> None:
        if not objs:
            return
        rows = []
        for obj in objs:
            pr = _promoted(obj)
            rows.append(
                {
                    "collection": collection,
                    "id": str(
                        getattr(obj, "id", None) or getattr(obj, "track_id", None) or _autoid(obj)
                    ),
                    "ts": pr["ts"],
                    "segment_id": pr["segment_id"],
                    "status": pr["status"],
                    "data": _dump(obj),
                }
            )
        with self.engine.begin() as conn:
            for row in rows:
                conn.execute(
                    delete(entities).where(
                        entities.c.collection == collection, entities.c.id == row["id"]
                    )
                )
                conn.execute(entities.insert().values(**row))

    # -- reads ------------------------------------------------------------ #
    def get(self, collection: str, id_: str, model: type[BaseModel]) -> Any | None:
        with self.engine.connect() as conn:
            r = conn.execute(
                select(entities.c.data).where(
                    entities.c.collection == collection, entities.c.id == id_
                )
            ).first()
        return model.model_validate(orjson.loads(r[0])) if r else None

    def find(
        self,
        collection: str,
        model: type[BaseModel],
        *,
        where: dict[str, Any] | None = None,
        order_by_ts: bool = False,
        desc: bool = False,
        limit: int | None = None,
    ) -> list[Any]:
        stmt = select(entities.c.data).where(entities.c.collection == collection)
        for key, val in (where or {}).items():
            col = getattr(entities.c, key, None)
            if col is not None:
                stmt = stmt.where(col == (str(val) if key == "status" else val))
        if order_by_ts:
            stmt = stmt.order_by(entities.c.ts.desc() if desc else entities.c.ts.asc())
        if limit:
            stmt = stmt.limit(limit)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [model.model_validate(orjson.loads(r[0])) for r in rows]

    def metrics_range(
        self,
        model: type[BaseModel],
        *,
        segment_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[Any]:
        stmt = select(entities.c.data).where(entities.c.collection == "segment_metric")
        if segment_id:
            stmt = stmt.where(entities.c.segment_id == segment_id)
        if start:
            stmt = stmt.where(entities.c.ts >= start)
        if end:
            stmt = stmt.where(entities.c.ts <= end)
        stmt = stmt.order_by(entities.c.ts.asc())
        if limit:
            stmt = stmt.limit(limit)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [model.model_validate(orjson.loads(r[0])) for r in rows]

    def latest_per_segment(self, model: type[BaseModel]) -> list[Any]:
        sub = (
            select(entities.c.segment_id, func.max(entities.c.ts).label("mts"))
            .where(entities.c.collection == "segment_metric")
            .group_by(entities.c.segment_id)
            .subquery()
        )
        stmt = (
            select(entities.c.data)
            .join(
                sub,
                (entities.c.segment_id == sub.c.segment_id) & (entities.c.ts == sub.c.mts),
            )
            .where(entities.c.collection == "segment_metric")
        )
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [model.model_validate(orjson.loads(r[0])) for r in rows]

    def count(self, collection: str, where: dict[str, Any] | None = None) -> int:
        stmt = select(func.count()).select_from(entities).where(entities.c.collection == collection)
        for key, val in (where or {}).items():
            col = getattr(entities.c, key, None)
            if col is not None:
                stmt = stmt.where(col == (str(val) if key == "status" else val))
        with self.engine.connect() as conn:
            return int(conn.execute(stmt).scalar() or 0)

    def clear(self, collection: str | None = None) -> None:
        with self.engine.begin() as conn:
            if collection:
                conn.execute(delete(entities).where(entities.c.collection == collection))
            else:
                conn.execute(delete(entities))


_autoid_counter = {"n": 0}


def _autoid(obj: BaseModel) -> str:
    _autoid_counter["n"] += 1
    return f"{obj.__class__.__name__}-{_autoid_counter['n']}"

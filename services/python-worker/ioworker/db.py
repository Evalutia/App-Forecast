from __future__ import annotations
import json

from dataclasses import dataclass
from typing import Dict, List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

@dataclass
class DBConfig:
    host: str
    port: int
    db: str
    user: str
    password: str


def get_engine(cfg: DBConfig) -> Engine:
    url = f"mysql+pymysql://{cfg.user}:{cfg.password}@{cfg.host}:{cfg.port}/{cfg.db}"
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600, future=True)
    return engine


def insert_job_start(engine: Engine, tipo_job: str = "forecast") -> int:
    sql = text(
        """
        INSERT INTO jobs_historial (tipo_job, estado, fecha_inicio)
        VALUES (:tipo_job, 'ejecutando', NOW(6))
        """
    )
    with engine.begin() as conn:
        res = conn.execute(sql, {"tipo_job": tipo_job})
        job_id = res.lastrowid
    return int(job_id)


def update_job_end(engine: Engine, job_id: int, estado: str, detalle: Dict) -> None:
    sql = text(
        """
        UPDATE jobs_historial
           SET estado = :estado,
               fecha_fin = NOW(6),
               detalle = :detalle
         WHERE id = :job_id
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, {"estado": estado, "detalle": json.dumps(detalle, ensure_ascii=False), "job_id": job_id})


def upsert_predicciones(engine: Engine, rows: List[Dict], job_id: Optional[int] = None) -> int:
    """
    Requiere índice único en (sku, modelo, version_modelo, fecha_predicha).
    Hace INSERT ... ON DUPLICATE KEY UPDATE.
    """
    if job_id is not None:
        for r in rows:
            r["job_id"] = job_id
    else:
        for r in rows:
            r.setdefault("job_id", None)
    sql = text(
    """
    INSERT INTO predicciones
        (sku, fecha_predicha, cantidad_predicha, modelo, version_modelo, horizonte, rmse, r2, job_id, ts_generacion)
    VALUES
        (:sku, :fecha_predicha, :cantidad_predicha, :modelo, :version_modelo, :horizonte, :rmse, :r2, :job_id, CURRENT_DATE)
    ON DUPLICATE KEY UPDATE
        cantidad_predicha = VALUES(cantidad_predicha),
        horizonte         = VALUES(horizonte),
        rmse              = VALUES(rmse),
        r2                = VALUES(r2),
        ts_generacion     = CURRENT_DATE,
        job_id            = VALUES(job_id),
        fecha_predicha = VALUES(fecha_predicha)
    """
    )
    with engine.begin() as conn:
        res = conn.execute(sql, rows)
        return len(rows)


def upsert_elegibilidad_metrics(engine: Engine, rows: List[Dict]) -> int:
    """
    Issue #72: persiste metricas crudas de walk-forward (r2_test, estable,
    n_folds, meses_historia) en articulos_elegibilidad_econometrico. No
    toca 'elegible' -- ese flag lo calcula #73 con el criterio completo de
    #70. Commit incremental (una transaccion por SKU, no un batch gigante):
    una corrida de horas sobre ~5500 SKUs no debe perder todo el progreso
    si se corta a mitad de camino, y queda naturalmente reanudable.
    """
    sql = text(
        """
        INSERT INTO articulos_elegibilidad_econometrico
            (sku, r2_test, estable, n_folds, meses_historia, evaluado_en)
        VALUES
            (:sku, :r2_test, :estable, :n_folds, :meses_historia, NOW(6))
        ON DUPLICATE KEY UPDATE
            r2_test        = VALUES(r2_test),
            estable        = VALUES(estable),
            n_folds        = VALUES(n_folds),
            meses_historia = VALUES(meses_historia),
            evaluado_en    = VALUES(evaluado_en)
        """
    )
    n = 0
    for r in rows:
        with engine.begin() as conn:
            conn.execute(sql, r)
        n += 1
    return n
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
import psycopg
from psycopg.rows import dict_row

@dataclass
class Metrics:
    db_ms: float = 0
    queries: int = 0

@contextmanager
def connection():
    # Connection parameters come from standard PG* environment variables.
    with psycopg.connect(autocommit=True, row_factory=dict_row,
                         options='-c search_path=denis_kuleshin') as conn:
        yield conn

class Store:
    def __init__(self, conn, metrics):
        self.conn = conn
        self.metrics = metrics

    def query(self, sql, params=()):
        start = perf_counter()
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall() if cur.description else []
        finally:
            self.metrics.db_ms += (perf_counter() - start) * 1000
            self.metrics.queries += 1

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

def get_store(request):
    # The annotation is applied in main.py; tests can override this dependency.
    with connection() as conn:
        yield Store(conn, request.state.metrics)

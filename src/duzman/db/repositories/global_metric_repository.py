"""Repository for append-only global metric persistence."""

from __future__ import annotations

from sqlalchemy.orm import Session

from duzman.collectors.records import GlobalMetricRecord
from duzman.db.models import GlobalMetric


class GlobalMetricRepository:
    """Persist normalized global metrics as append-only time-series rows."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def insert_one(self, record: GlobalMetricRecord) -> GlobalMetric:
        """Insert one global metric record and return the ORM row."""
        row = GlobalMetric(
            ts=record.ts,
            metric_name=record.metric_name,
            value=record.value,
        )
        self.session.add(row)
        self.session.flush()
        return row

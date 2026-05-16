"""Repository for upserting normalized ETF flow records."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from duzman.collectors.records import ETFFlowRecord
from duzman.db.models import EtfFlow


class ETFFlowRepository:
    """Persist ETF flows using the table primary key as the upsert identity."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_many(self, records: Sequence[ETFFlowRecord]) -> int:
        """Upsert ETF flow records and return the number of records processed."""
        for record in records:
            self.session.merge(
                EtfFlow(
                    date=record.date,
                    asset=record.asset,
                    provider=record.provider,
                    flow_usd_m=record.flow_usd_m,
                )
            )
        self.session.flush()
        return len(records)

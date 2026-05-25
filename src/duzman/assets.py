# src/duzman/assets.py
# Stage A asset constants shared by schedulers and migration seed logic.

"""Canonical Stage A asset symbols for scheduler jobs, migrations, and seeds.

Adding a new Stage A asset means editing `STAGE_A_ASSETS` and adding a new
idempotent seed migration entry in the same PR.
"""

STAGE_A_ASSETS: tuple[str, ...] = ("BTC", "ETH", "SOL", "SUI", "TON", "UNI")

STAGE_A_ASSET_NAMES: dict[str, str] = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "SUI": "Sui",
    "TON": "Toncoin",
    "UNI": "Uniswap",
}

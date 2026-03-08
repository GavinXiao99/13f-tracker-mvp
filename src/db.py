"""Database helpers for 13F Tracker MVP."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path("data/13f.db")


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection and ensure schema exists."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create required tables when they do not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS institutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cik TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            institution_id INTEGER NOT NULL,
            cusip TEXT NOT NULL,
            issuer TEXT NOT NULL,
            value_usd INTEGER NOT NULL,
            shares INTEGER NOT NULL,
            report_date TEXT NOT NULL,
            FOREIGN KEY (institution_id) REFERENCES institutions (id)
        )
        """
    )
    conn.commit()


def load_sample_data() -> None:
    """Insert two mock institutions and holdings for demo."""
    with get_connection() as conn:
        institutions = [
            ("0001067983", "Berkshire Hathaway Inc."),
            ("0001350694", "Bridgewater Associates, LP"),
        ]
        conn.executemany(
            """
            INSERT INTO institutions (cik, name)
            VALUES (?, ?)
            ON CONFLICT(cik) DO UPDATE SET name = excluded.name
            """,
            institutions,
        )

        institution_map = {
            row["cik"]: row["id"]
            for row in conn.execute("SELECT id, cik FROM institutions").fetchall()
        }

        holdings = [
            (
                institution_map["0001067983"],
                "037833100",
                "Apple Inc.",
                120000000,
                500000,
                "2024-12-31",
            ),
            (
                institution_map["0001067983"],
                "02079K305",
                "Alphabet Inc. Class A",
                65000000,
                350000,
                "2024-12-31",
            ),
            (
                institution_map["0001350694"],
                "594918104",
                "Microsoft Corp.",
                90000000,
                250000,
                "2024-12-31",
            ),
            (
                institution_map["0001350694"],
                "88160R101",
                "Tesla Inc.",
                30000000,
                120000,
                "2024-12-31",
            ),
        ]

        conn.execute("DELETE FROM holdings")
        conn.executemany(
            """
            INSERT INTO holdings (
                institution_id, cusip, issuer, value_usd, shares, report_date
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            holdings,
        )
        conn.commit()


def fetch_institutions() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, cik, name FROM institutions ORDER BY name"
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_holdings_by_institution(institution_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT issuer, cusip, value_usd, shares, report_date
            FROM holdings
            WHERE institution_id = ?
            ORDER BY value_usd DESC
            """,
            (institution_id,),
        ).fetchall()
    return [dict(row) for row in rows]

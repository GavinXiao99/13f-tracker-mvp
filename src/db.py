"""Database helpers for 13F Tracker MVP."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

DB_PATH = Path("data/13f.db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _migrate_legacy_holdings(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(holdings)").fetchall()
    }
    if not columns or "filing_id" in columns:
        return

    conn.execute("ALTER TABLE holdings RENAME TO holdings_legacy")
    conn.execute(
        """
        CREATE TABLE holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filing_id INTEGER NOT NULL,
            issuer TEXT NOT NULL,
            cusip TEXT NOT NULL,
            value INTEGER NOT NULL,
            ssh_prnamt INTEGER NOT NULL,
            ssh_prnamt_type TEXT,
            put_call TEXT,
            investment_discretion TEXT,
            voting_sole INTEGER,
            voting_shared INTEGER,
            voting_none INTEGER,
            FOREIGN KEY (filing_id) REFERENCES filings (id)
        )
        """
    )

    legacy_rows = conn.execute(
        """
        SELECT institution_id, report_date, issuer, cusip, value_usd, shares
        FROM holdings_legacy
        ORDER BY institution_id, report_date
        """
    ).fetchall()

    filing_map: dict[tuple[int, str], int] = {}
    for row in legacy_rows:
        key = (row["institution_id"], row["report_date"])
        if key not in filing_map:
            accession = f"MOCK-{row['institution_id']}-{row['report_date']}"
            filing_id = conn.execute(
                """
                INSERT INTO filings (institution_id, accession, filing_date, report_period, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row["institution_id"],
                    accession,
                    row["report_date"],
                    row["report_date"],
                    datetime.utcnow().isoformat(timespec="seconds"),
                ),
            ).lastrowid
            filing_map[key] = filing_id

        conn.execute(
            """
            INSERT INTO holdings (
                filing_id, issuer, cusip, value, ssh_prnamt, ssh_prnamt_type,
                put_call, investment_discretion, voting_sole, voting_shared, voting_none
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filing_map[key],
                row["issuer"],
                row["cusip"],
                row["value_usd"],
                row["shares"],
                "SH",
                None,
                None,
                None,
                None,
                None,
            ),
        )

    conn.execute("DROP TABLE holdings_legacy")


def init_db(conn: sqlite3.Connection) -> None:
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
        CREATE TABLE IF NOT EXISTS filings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            institution_id INTEGER NOT NULL,
            accession TEXT UNIQUE NOT NULL,
            filing_date TEXT NOT NULL,
            report_period TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (institution_id) REFERENCES institutions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filing_id INTEGER NOT NULL,
            issuer TEXT NOT NULL,
            cusip TEXT NOT NULL,
            value INTEGER NOT NULL,
            ssh_prnamt INTEGER NOT NULL,
            ssh_prnamt_type TEXT,
            put_call TEXT,
            investment_discretion TEXT,
            voting_sole INTEGER,
            voting_shared INTEGER,
            voting_none INTEGER,
            FOREIGN KEY (filing_id) REFERENCES filings (id)
        )
        """
    )
    _migrate_legacy_holdings(conn)
    conn.commit()


def _upsert_institution(conn: sqlite3.Connection, cik: str, name: str) -> int:
    conn.execute(
        """
        INSERT INTO institutions (cik, name)
        VALUES (?, ?)
        ON CONFLICT(cik) DO UPDATE SET name = excluded.name
        """,
        (cik, name),
    )
    row = conn.execute("SELECT id FROM institutions WHERE cik = ?", (cik,)).fetchone()
    return int(row["id"])


def save_filing_and_holdings(
    cik: str,
    institution_name: str,
    accession: str,
    filing_date: str,
    report_period: str | None,
    holdings_df: pd.DataFrame,
) -> int:
    with get_connection() as conn:
        institution_id = _upsert_institution(conn, cik, institution_name)
        conn.execute("DELETE FROM holdings WHERE filing_id IN (SELECT id FROM filings WHERE accession = ?)", (accession,))
        conn.execute("DELETE FROM filings WHERE accession = ?", (accession,))

        filing_id = conn.execute(
            """
            INSERT INTO filings (institution_id, accession, filing_date, report_period, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                institution_id,
                accession,
                filing_date,
                report_period,
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        ).lastrowid

        rows = [
            (
                filing_id,
                row.issuer,
                row.cusip,
                int(row.value),
                int(row.sshPrnamt),
                row.sshPrnamtType,
                row.putCall,
                row.investmentDiscretion,
                int(row.votingSole) if pd.notna(row.votingSole) else None,
                int(row.votingShared) if pd.notna(row.votingShared) else None,
                int(row.votingNone) if pd.notna(row.votingNone) else None,
            )
            for row in holdings_df.itertuples(index=False)
        ]

        conn.executemany(
            """
            INSERT INTO holdings (
                filing_id, issuer, cusip, value, ssh_prnamt, ssh_prnamt_type,
                put_call, investment_discretion, voting_sole, voting_shared, voting_none
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        return int(filing_id)


def load_sample_data() -> None:
    sample = [
        {
            "cik": "0001067983",
            "name": "Berkshire Hathaway Inc.",
            "accession": "MOCK-0001067983-20241231",
            "filing_date": "2025-02-14",
            "report_period": "2024-12-31",
            "holdings": pd.DataFrame(
                [
                    {
                        "issuer": "Apple Inc.",
                        "cusip": "037833100",
                        "value": 120000000,
                        "sshPrnamt": 500000,
                        "sshPrnamtType": "SH",
                        "putCall": None,
                        "investmentDiscretion": "SOLE",
                        "votingSole": 500000,
                        "votingShared": 0,
                        "votingNone": 0,
                    },
                    {
                        "issuer": "Alphabet Inc. Class A",
                        "cusip": "02079K305",
                        "value": 65000000,
                        "sshPrnamt": 350000,
                        "sshPrnamtType": "SH",
                        "putCall": None,
                        "investmentDiscretion": "SOLE",
                        "votingSole": 350000,
                        "votingShared": 0,
                        "votingNone": 0,
                    },
                ]
            ),
        },
        {
            "cik": "0001350694",
            "name": "Bridgewater Associates, LP",
            "accession": "MOCK-0001350694-20241231",
            "filing_date": "2025-02-14",
            "report_period": "2024-12-31",
            "holdings": pd.DataFrame(
                [
                    {
                        "issuer": "Microsoft Corp.",
                        "cusip": "594918104",
                        "value": 90000000,
                        "sshPrnamt": 250000,
                        "sshPrnamtType": "SH",
                        "putCall": None,
                        "investmentDiscretion": "SOLE",
                        "votingSole": 250000,
                        "votingShared": 0,
                        "votingNone": 0,
                    },
                    {
                        "issuer": "Tesla Inc.",
                        "cusip": "88160R101",
                        "value": 30000000,
                        "sshPrnamt": 120000,
                        "sshPrnamtType": "SH",
                        "putCall": None,
                        "investmentDiscretion": "SOLE",
                        "votingSole": 120000,
                        "votingShared": 0,
                        "votingNone": 0,
                    },
                ]
            ),
        },
    ]

    with get_connection() as conn:
        conn.execute("DELETE FROM holdings")
        conn.execute("DELETE FROM filings")
        conn.execute("DELETE FROM institutions")
        conn.commit()

    for item in sample:
        save_filing_and_holdings(
            cik=item["cik"],
            institution_name=item["name"],
            accession=item["accession"],
            filing_date=item["filing_date"],
            report_period=item["report_period"],
            holdings_df=item["holdings"],
        )


def fetch_institutions() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, cik, name FROM institutions ORDER BY name").fetchall()
    return [dict(row) for row in rows]


def fetch_filings_by_institution(institution_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, accession, filing_date, report_period, created_at
            FROM filings
            WHERE institution_id = ?
            ORDER BY filing_date DESC
            """,
            (institution_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_holdings_by_filing(filing_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT issuer, cusip, value, ssh_prnamt, ssh_prnamt_type,
                   put_call, investment_discretion, voting_sole, voting_shared, voting_none
            FROM holdings
            WHERE filing_id = ?
            ORDER BY value DESC
            """,
            (filing_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_holdings_by_institution(institution_id: int) -> list[dict[str, Any]]:
    filings = fetch_filings_by_institution(institution_id)
    if not filings:
        return []
    return fetch_holdings_by_filing(int(filings[0]["id"]))

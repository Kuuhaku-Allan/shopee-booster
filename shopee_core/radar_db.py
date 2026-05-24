"""
shopee_core/radar_db.py - SQLite foundation for the assisted competitor radar.

This module owns only schema creation and low-level connection helpers. Business
rules live in radar_service.py.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.getenv("SHOPEE_RADAR_DB_PATH", _BASE / "data" / "radar.db"))


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection configured for radar data."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create radar tables and indexes when they do not exist."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radar_products (
                product_uid TEXT PRIMARY KEY,
                owner_user_id TEXT,
                source_type TEXT NOT NULL,
                marketplace TEXT NOT NULL,
                url TEXT NOT NULL,
                canonical_url TEXT UNIQUE,
                title TEXT,
                price REAL,
                shop_name TEXT,
                niche TEXT,
                status TEXT NOT NULL,
                relevance_score REAL DEFAULT 0,
                rejection_reason TEXT,
                raw_json TEXT,
                created_at TEXT,
                updated_at TEXT,
                collected_at TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radar_assets (
                asset_uid TEXT PRIMARY KEY,
                product_uid TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                source_url TEXT,
                local_path TEXT,
                created_at TEXT,
                FOREIGN KEY (product_uid) REFERENCES radar_products(product_uid)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radar_reviews (
                review_uid TEXT PRIMARY KEY,
                product_uid TEXT NOT NULL,
                rating REAL,
                text TEXT,
                author TEXT,
                created_at TEXT,
                raw_json TEXT,
                FOREIGN KEY (product_uid) REFERENCES radar_products(product_uid)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radar_collection_jobs (
                job_uid TEXT PRIMARY KEY,
                product_uid TEXT NOT NULL,
                url TEXT NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                last_error TEXT,
                created_at TEXT,
                updated_at TEXT,
                finished_at TEXT,
                FOREIGN KEY (product_uid) REFERENCES radar_products(product_uid)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radar_competitor_matches (
                match_uid TEXT PRIMARY KEY,
                own_product_uid TEXT NOT NULL,
                candidate_product_uid TEXT NOT NULL,
                verdict TEXT NOT NULL,
                relevance_score REAL NOT NULL,
                confidence TEXT,
                reasons_json TEXT,
                signals_json TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(own_product_uid, candidate_product_uid),
                FOREIGN KEY (own_product_uid) REFERENCES radar_products(product_uid),
                FOREIGN KEY (candidate_product_uid) REFERENCES radar_products(product_uid)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radar_pattern_reports (
                report_uid TEXT PRIMARY KEY,
                own_product_uid TEXT NOT NULL,
                total_competitors INTEGER NOT NULL,
                direct_count INTEGER NOT NULL,
                partial_count INTEGER DEFAULT 0,
                price_min REAL,
                price_max REAL,
                price_avg REAL,
                price_median REAL,
                title_terms_json TEXT,
                feature_terms_json TEXT,
                description_patterns_json TEXT,
                image_patterns_json TEXT,
                warnings_json TEXT,
                recommendations_json TEXT,
                raw_json TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (own_product_uid) REFERENCES radar_products(product_uid)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radar_candidate_links (
                link_uid TEXT PRIMARY KEY,
                own_product_uid TEXT NOT NULL,
                candidate_product_uid TEXT NOT NULL,
                source TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(own_product_uid, candidate_product_uid),
                FOREIGN KEY (own_product_uid) REFERENCES radar_products(product_uid),
                FOREIGN KEY (candidate_product_uid) REFERENCES radar_products(product_uid)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radar_stores (
                store_uid TEXT PRIMARY KEY,
                shop_uid TEXT,
                shop_slug TEXT,
                shop_name TEXT,
                marketplace TEXT,
                source_url TEXT,
                last_snapshot_at TEXT,
                last_successful_load_at TEXT,
                product_count INTEGER DEFAULT 0,
                raw_json TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radar_store_products (
                store_product_uid TEXT PRIMARY KEY,
                store_uid TEXT NOT NULL,
                radar_product_uid TEXT,
                marketplace_product_id TEXT,
                canonical_url TEXT,
                title TEXT NOT NULL,
                price REAL,
                image_url TEXT,
                status TEXT,
                first_seen_at TEXT,
                last_seen_at TEXT,
                last_changed_at TEXT,
                raw_json TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (store_uid) REFERENCES radar_stores(store_uid),
                FOREIGN KEY (radar_product_uid) REFERENCES radar_products(product_uid)
            )
            """
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_products_source_type "
            "ON radar_products(source_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_products_marketplace "
            "ON radar_products(marketplace)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_products_status "
            "ON radar_products(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_products_owner_user_id "
            "ON radar_products(owner_user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_assets_product_uid "
            "ON radar_assets(product_uid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_reviews_product_uid "
            "ON radar_reviews(product_uid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_jobs_product_uid "
            "ON radar_collection_jobs(product_uid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_jobs_status "
            "ON radar_collection_jobs(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_matches_own_product_uid "
            "ON radar_competitor_matches(own_product_uid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_matches_candidate_product_uid "
            "ON radar_competitor_matches(candidate_product_uid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_matches_verdict "
            "ON radar_competitor_matches(verdict)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_pattern_reports_own_product_uid "
            "ON radar_pattern_reports(own_product_uid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_candidate_links_own_product_uid "
            "ON radar_candidate_links(own_product_uid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_candidate_links_candidate_product_uid "
            "ON radar_candidate_links(candidate_product_uid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_pattern_reports_created_at "
            "ON radar_pattern_reports(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_stores_shop_uid "
            "ON radar_stores(shop_uid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_stores_shop_slug "
            "ON radar_stores(shop_slug)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_stores_marketplace "
            "ON radar_stores(marketplace)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_store_products_store_uid "
            "ON radar_store_products(store_uid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_store_products_radar_product_uid "
            "ON radar_store_products(radar_product_uid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_store_products_marketplace_product_id "
            "ON radar_store_products(marketplace_product_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_store_products_canonical_url "
            "ON radar_store_products(canonical_url)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_radar_store_products_status "
            "ON radar_store_products(status)"
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_radar_store_products_store_marketplace_id
            ON radar_store_products(store_uid, marketplace_product_id)
            WHERE marketplace_product_id IS NOT NULL AND marketplace_product_id != ''
            """
        )

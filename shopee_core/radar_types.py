"""
shopee_core/radar_types.py - Data contracts for the assisted competitor radar.

R1 is only the persistent foundation: products, assets, reviews and collection
jobs. No browser automation or scraping code belongs here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


RadarSourceType = Literal[
    "own_product",
    "competitor_candidate",
    "competitor_direct",
    "competitor_partial",
    "rejected",
]

RadarMarketplace = Literal["shopee", "mercadolivre", "unknown"]

RadarProductStatus = Literal[
    "pending",
    "collecting",
    "collected",
    "failed",
    "rejected",
]

RadarAssetType = Literal["image", "video", "description_image", "thumbnail"]

RadarJobType = Literal["collect_product_page", "refresh_product_page"]

RadarJobStatus = Literal["pending", "running", "done", "failed"]


SOURCE_TYPES = {
    "own_product",
    "competitor_candidate",
    "competitor_direct",
    "competitor_partial",
    "rejected",
}

MARKETPLACES = {"shopee", "mercadolivre", "unknown"}

PRODUCT_STATUSES = {"pending", "collecting", "collected", "failed", "rejected"}

ASSET_TYPES = {"image", "video", "description_image", "thumbnail"}

JOB_TYPES = {"collect_product_page", "refresh_product_page"}

JOB_STATUSES = {"pending", "running", "done", "failed"}


@dataclass
class RadarProduct:
    product_uid: str
    source_type: RadarSourceType
    marketplace: RadarMarketplace
    url: str
    owner_user_id: Optional[str] = None
    canonical_url: Optional[str] = None
    title: Optional[str] = None
    price: Optional[float] = None
    shop_name: Optional[str] = None
    niche: Optional[str] = None
    status: RadarProductStatus = "pending"
    relevance_score: float = 0
    rejection_reason: Optional[str] = None
    raw_json: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    collected_at: Optional[str] = None


@dataclass
class RadarAsset:
    asset_uid: str
    product_uid: str
    asset_type: RadarAssetType
    source_url: Optional[str] = None
    local_path: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class RadarReview:
    review_uid: str
    product_uid: str
    rating: Optional[float] = None
    text: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[str] = None
    raw_json: Optional[str] = None


@dataclass
class RadarCollectionJob:
    job_uid: str
    product_uid: str
    url: str
    job_type: RadarJobType
    status: RadarJobStatus = "pending"
    attempts: int = 0
    last_error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    finished_at: Optional[str] = None


@dataclass
class AddProductUrlResult:
    created: bool
    duplicate: bool
    product: RadarProduct
    job: Optional[RadarCollectionJob] = None


@dataclass
class BulkAddProductUrlResult:
    total_received: int
    created: int
    duplicates: int
    invalid: int
    products: list[RadarProduct] = field(default_factory=list)
    jobs: list[RadarCollectionJob] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

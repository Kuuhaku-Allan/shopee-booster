"""
shopee_core/radar_assets_service.py - Radar asset download helpers.

R3 downloads Mercado Livre product media to disk and registers the local file
paths in radar_assets. It does not run browser automation or image analysis.
"""

from __future__ import annotations

import mimetypes
import re
import unicodedata
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from .radar_service import add_product_asset, get_product, list_product_assets
from .radar_types import ASSET_TYPES


BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_BASE_DIR = BASE_DIR / "data" / "radar_assets"

_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}
_ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".avif",
    ".mp4",
    ".webm",
}
_ASSET_DIRS = {
    "image": "images",
    "thumbnail": "images",
    "description_image": "images",
    "video": "videos",
}
_ASSET_PREFIXES = {
    "image": "image",
    "thumbnail": "thumbnail",
    "description_image": "description_image",
    "video": "video",
}


class _HttpResponse:
    def __init__(self, status_code: int, content: bytes, headers: dict[str, str]):
        self.status_code = status_code
        self.content = content
        self.headers = headers


class _HttpClient:
    def get(self, url: str, timeout: int = 30, headers: dict | None = None) -> _HttpResponse:
        request = Request(url, headers=headers or {})
        with urlopen(request, timeout=timeout) as response:
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return _HttpResponse(
                status_code=getattr(response, "status", 200),
                content=response.read(),
                headers=response_headers,
            )


requests = _HttpClient()


def sanitize_filename(text: str) -> str:
    """Return a filesystem-safe ASCII filename stem."""
    if text is None:
        return "asset"

    normalized = unicodedata.normalize("NFKD", str(text))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_text).strip("._-")
    clean = re.sub(r"_+", "_", clean)
    return (clean or "asset")[:120]


def guess_extension_from_url_or_content_type(url, content_type) -> str:
    """Guess an asset file extension from URL path or HTTP content type."""
    try:
        suffix = Path(urlsplit(str(url or "")).path).suffix.lower()
    except Exception:
        suffix = ""

    if suffix in _ALLOWED_EXTENSIONS:
        return ".jpg" if suffix == ".jpeg" else suffix

    clean_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if clean_content_type in _CONTENT_TYPE_EXTENSIONS:
        return _CONTENT_TYPE_EXTENSIONS[clean_content_type]

    guessed = mimetypes.guess_extension(clean_content_type or "")
    if guessed in _ALLOWED_EXTENSIONS:
        return ".jpg" if guessed == ".jpeg" else guessed

    return ".bin"


def download_asset(
    url: str,
    product_uid: str,
    asset_type: str,
    timeout: int | float = 30,
) -> dict:
    """Download one asset and register its local path in radar_assets."""
    if asset_type not in ASSET_TYPES:
        allowed = ", ".join(sorted(ASSET_TYPES))
        raise ValueError(f"asset_type invalido: {asset_type!r}. Use: {allowed}")

    product = get_product(product_uid)
    if not product:
        raise ValueError(f"Produto nao encontrado: {product_uid}")

    clean_url = str(url or "").strip()
    if not clean_url.startswith(("http://", "https://")):
        raise ValueError(f"URL de asset invalida: {url!r}")

    existing = _existing_downloaded_asset(product_uid, asset_type, clean_url)
    if existing:
        existing["downloaded"] = False
        return existing

    response = requests.get(
        clean_url,
        timeout=timeout,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        },
    )
    status_code = getattr(response, "status_code", 0)
    if status_code < 200 or status_code >= 300:
        raise RuntimeError(f"Falha ao baixar asset ({status_code}): {clean_url}")

    content = getattr(response, "content", b"")
    if not content:
        raise RuntimeError(f"Asset vazio: {clean_url}")

    content_type = getattr(response, "headers", {}).get("content-type")
    extension = guess_extension_from_url_or_content_type(clean_url, content_type)
    target_dir = _target_dir(product_uid, asset_type)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = _next_asset_path(target_dir, asset_type, extension)
    target_path.write_bytes(content)

    asset = add_product_asset(
        product_uid,
        asset_type,
        source_url=clean_url,
        local_path=str(target_path),
    )
    asset["downloaded"] = True
    return asset


def download_product_images(product_uid: str, image_urls: list[str]) -> list[dict]:
    """Download all unique image URLs for one product."""
    assets = []
    seen = set()

    for image_url in image_urls or []:
        clean_url = str(image_url or "").strip()
        if not clean_url or clean_url in seen:
            continue
        seen.add(clean_url)
        try:
            assets.append(download_asset(clean_url, product_uid, "image"))
        except Exception as exc:
            assets.append(_download_error(product_uid, "image", clean_url, exc))

    return assets


def _existing_downloaded_asset(
    product_uid: str,
    asset_type: str,
    source_url: str,
) -> dict | None:
    for asset in list_product_assets(product_uid, asset_type):
        if asset.get("source_url") != source_url:
            continue
        local_path = asset.get("local_path")
        if local_path and Path(local_path).exists():
            return dict(asset)
    return None


def _target_dir(product_uid: str, asset_type: str) -> Path:
    safe_product_uid = sanitize_filename(product_uid)
    return ASSETS_BASE_DIR / safe_product_uid / _ASSET_DIRS.get(asset_type, "assets")


def _next_asset_path(target_dir: Path, asset_type: str, extension: str) -> Path:
    prefix = _ASSET_PREFIXES.get(asset_type, "asset")
    for index in range(1, 10000):
        candidate = target_dir / f"{prefix}_{index:03d}{extension}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Nao foi possivel gerar nome de arquivo em {target_dir}")


def _download_error(
    product_uid: str,
    asset_type: str,
    source_url: str,
    exc: Exception,
) -> dict:
    return {
        "product_uid": product_uid,
        "asset_type": asset_type,
        "source_url": source_url,
        "local_path": None,
        "downloaded": False,
        "error": str(exc),
    }

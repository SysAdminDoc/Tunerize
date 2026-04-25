"""Online SoundFont library browser — search public libraries, download into the local SF2 folder.

v0.2.0 ships one provider:
    - musical-artifacts.com  (REST/JSON, per-artifact license, direct file URL)

The `Provider` protocol is the integration point. Future providers can include
Reddit r/soundfonts trending, Polyphone if/when their API opens, and a GitHub
topic search for `topic:soundfont`.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlencode, urlparse

import requests

from app import __version__

USER_AGENT = f"Tunerize/{__version__} (+https://github.com/SysAdminDoc/Tunerize)"
DEFAULT_TIMEOUT = 20  # seconds


class BrowserError(Exception):
    pass


@dataclass(frozen=True)
class SoundFontResult:
    source: str                      # e.g. "musical-artifacts.com"
    name: str
    author: str | None
    description: str
    license: str
    file_url: str
    file_size_bytes: int | None
    tags: tuple[str, ...]
    download_count: int | None
    detail_url: str                  # human-readable web page
    file_hash: str | None = None


class Provider(Protocol):
    """Protocol every browser source must satisfy."""

    name: str

    def search(self, query: str = "", *, limit: int = 50) -> list[SoundFontResult]: ...


# ---------- musical-artifacts.com ----------

class MusicalArtifactsProvider:
    """Client for musical-artifacts.com REST/JSON API.

    Docs: https://github.com/lfzawacki/musical-artifacts/wiki/API-Documentation
    Rate limit: 60 req/min unauthenticated. Cached locally to stay well under.
    """

    name = "musical-artifacts.com"
    BASE_URL = "https://musical-artifacts.com"

    def __init__(
        self,
        session: requests.Session | None = None,
        cache_dir: Path | None = None,
        cache_ttl_seconds: int = 3600,
    ):
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/json")
        self._cache_dir = cache_dir
        self._cache_ttl = cache_ttl_seconds
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def search(self, query: str = "", *, limit: int = 50) -> list[SoundFontResult]:
        params: dict[str, str] = {"tag": "soundfont"}
        if query:
            params["q"] = query

        cache_key = self._cache_key("artifacts", params)
        cached = self._get_cache(cache_key)
        if cached is not None:
            data = cached
        else:
            url = f"{self.BASE_URL}/artifacts.json"
            try:
                r = self._session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
                r.raise_for_status()
            except requests.RequestException as e:
                raise BrowserError(f"musical-artifacts.com fetch failed: {e}") from e
            try:
                data = r.json()
            except ValueError as e:
                raise BrowserError(f"musical-artifacts.com returned non-JSON: {e}") from e
            self._set_cache(cache_key, data)

        if not isinstance(data, list):
            raise BrowserError("Unexpected response shape from musical-artifacts.com")

        results: list[SoundFontResult] = []
        for item in data[:limit]:
            tags_field = item.get("tags") or []
            tag_strs = tuple(
                t["name"] if isinstance(t, dict) and "name" in t else str(t)
                for t in tags_field
            )
            results.append(
                SoundFontResult(
                    source=self.name,
                    name=item.get("name") or "(unnamed)",
                    author=item.get("author"),
                    description=(item.get("description") or "").strip(),
                    license=item.get("license") or "Unknown",
                    file_url=item.get("file") or "",
                    file_size_bytes=_safe_int(item.get("file_size")),
                    tags=tag_strs,
                    download_count=_safe_int(item.get("download_count")),
                    detail_url=item.get("url") or f"{self.BASE_URL}/artifacts/{item.get('id', '')}",
                    file_hash=item.get("file_hash"),
                )
            )

        return [r for r in results if r.file_url and self._looks_like_soundfont(r)]

    # ----- helpers -----

    @staticmethod
    def _looks_like_soundfont(r: SoundFontResult) -> bool:
        url = r.file_url.lower()
        if any(url.endswith(ext) for ext in (".sf2", ".sf3", ".sfz")):
            return True
        # Some artifacts ship .zip / .7z bundles — keep when soundfont-tagged
        tags_lower = tuple(t.lower() for t in r.tags)
        return any(t in tags_lower for t in ("soundfont", "sf2", "sf3"))

    def _cache_key(self, endpoint: str, params: dict) -> str:
        raw = endpoint + "?" + urlencode(sorted(params.items()))
        return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()

    def _get_cache(self, key: str):
        if self._cache_dir is None:
            return None
        path = self._cache_dir / f"{key}.json"
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self._cache_ttl:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _set_cache(self, key: str, data) -> None:
        if self._cache_dir is None:
            return
        path = self._cache_dir / f"{key}.json"
        try:
            path.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass


# ---------- downloader ----------

def download_to_library(
    result: SoundFontResult,
    library_dir: Path,
    *,
    progress: Callable[[int, int | None], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    chunk_size: int = 65536,
    session: requests.Session | None = None,
) -> Path:
    """Stream-download a `SoundFontResult` into `library_dir`.

    Validates RIFF/sfbk header for `.sf2`/`.sf3` files. Bundles (`.zip`/`.7z`)
    are saved as-is — the user unpacks manually.
    """
    library_dir.mkdir(parents=True, exist_ok=True)
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", USER_AGENT)

    try:
        r = sess.get(result.file_url, stream=True, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        raise BrowserError(f"Download failed: {e}") from e

    total = result.file_size_bytes or _content_length(r)

    filename = _filename_from_url(result.file_url) or (_safe_filename(result.name) + ".sf2")
    dest = library_dir / filename
    if dest.exists():
        i = 1
        stem, suffix = dest.stem, dest.suffix
        while True:
            alt = library_dir / f"{stem}__{i}{suffix}"
            if not alt.exists():
                dest = alt
                break
            i += 1

    tmp = dest.with_suffix(dest.suffix + ".part")
    downloaded = 0
    try:
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if cancel_check is not None and cancel_check():
                    raise BrowserError("Download cancelled by user.")
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if progress is not None:
                    progress(downloaded, total)

        if dest.suffix.lower() in (".sf2", ".sf3"):
            from app.core.soundfonts import validate_sf2
            ok, err = validate_sf2(tmp)
            if not ok:
                raise BrowserError(f"Downloaded file failed SoundFont validation: {err}")

        shutil.move(str(tmp), str(dest))
        return dest
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _content_length(r) -> int | None:
    cl = r.headers.get("Content-Length")
    return int(cl) if cl and cl.isdigit() else None


def _filename_from_url(url: str) -> str | None:
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    return name if name and "." in name else None


def _safe_filename(name: str) -> str:
    keep = "-_.() "
    out = "".join(c for c in name if c.isalnum() or c in keep).strip()
    return out or "soundfont"


def _safe_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

"""Online SoundFont library browser — search public libraries, download into the local SF2 folder.

v0.2.0 started with one provider:
    - musical-artifacts.com  (REST/JSON, per-artifact license, direct file URL)
    - github.com topic:soundfont (repository search, archive downloads)

The `Provider` protocol is the integration point. Future providers can include
Reddit r/soundfonts trending and Polyphone if/when their API opens.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, unquote, urlencode, urlparse

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
    download_name: str | None = None


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
        return _looks_like_soundfont(r)

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
        with suppress(OSError):
            path.write_text(json.dumps(data), encoding="utf-8")


# ---------- github.com ----------

class GitHubTopicProvider:
    """Search public GitHub repositories tagged `soundfont`.

    Results install as repository ZIP bundles because GitHub repositories can
    contain many SoundFont files. The user can unpack the bundle and import any
    `.sf2` / `.sf3` files inside.
    """

    name = "github.com"
    API_URL = "https://api.github.com/search/repositories"

    def __init__(
        self,
        session: requests.Session | None = None,
        cache_dir: Path | None = None,
        cache_ttl_seconds: int = 3600,
    ):
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)
        self._session.headers.setdefault("Accept", "application/vnd.github+json")
        self._cache_dir = cache_dir
        self._cache_ttl = cache_ttl_seconds
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def search(self, query: str = "", *, limit: int = 30) -> list[SoundFontResult]:
        params = {
            "q": _github_query(query),
            "sort": "stars",
            "order": "desc",
            "per_page": str(min(max(limit, 1), 50)),
        }
        cache_key = self._cache_key("repositories", params)
        cached = self._get_cache(cache_key)
        if cached is not None:
            data = cached
        else:
            try:
                r = self._session.get(self.API_URL, params=params, timeout=DEFAULT_TIMEOUT)
                r.raise_for_status()
            except requests.RequestException as e:
                raise BrowserError(f"GitHub repository search failed: {e}") from e
            try:
                data = r.json()
            except ValueError as e:
                raise BrowserError(f"GitHub returned non-JSON: {e}") from e
            self._set_cache(cache_key, data)

        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise BrowserError("Unexpected response shape from GitHub")

        results: list[SoundFontResult] = []
        for item in items[:limit]:
            full_name = item.get("full_name") or item.get("name") or "(unnamed)"
            owner = item.get("owner") or {}
            owner_login = owner.get("login") if isinstance(owner, dict) else None
            branch = item.get("default_branch") or "main"
            archive_url = item.get("zipball_url") or ""
            if not archive_url and "/" in full_name:
                archive_url = f"https://api.github.com/repos/{full_name}/zipball/{quote(branch, safe='')}"

            license_info = item.get("license")
            license_label = "Unknown"
            if isinstance(license_info, dict):
                license_label = license_info.get("spdx_id") or license_info.get("name") or "Unknown"

            tags = ("soundfont", "github", "bundle")
            language = item.get("language")
            if language:
                tags = (*tags, str(language))

            description = (item.get("description") or "").strip()
            results.append(
                SoundFontResult(
                    source=self.name,
                    name=full_name,
                    author=owner_login,
                    description=(
                        description
                        or "GitHub repository tagged with topic:soundfont. Downloads as a ZIP bundle."
                    ),
                    license=license_label,
                    file_url=archive_url,
                    file_size_bytes=None,
                    tags=tags,
                    download_count=_safe_int(item.get("stargazers_count")),
                    detail_url=item.get("html_url") or "",
                    download_name=f"{_safe_filename(full_name.replace('/', ' - '))}.zip",
                )
            )

        return [r for r in results if r.file_url and _looks_like_soundfont(r)]

    def _cache_key(self, endpoint: str, params: dict) -> str:
        raw = endpoint + "?" + urlencode(sorted(params.items()))
        return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()

    def _get_cache(self, key: str):
        if self._cache_dir is None:
            return None
        path = self._cache_dir / f"github-{key}.json"
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
        path = self._cache_dir / f"github-{key}.json"
        with suppress(OSError):
            path.write_text(json.dumps(data), encoding="utf-8")


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

    filename = result.download_name or _filename_from_url(result.file_url) or (_safe_filename(result.name) + ".sf2")
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
            with suppress(OSError):
                tmp.unlink()


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


def _looks_like_soundfont(r: SoundFontResult) -> bool:
    url = r.file_url.lower()
    if any(url.endswith(ext) for ext in (".sf2", ".sf3", ".sfz", ".zip", ".7z")):
        return True
    tags_lower = tuple(t.lower() for t in r.tags)
    return any(t in tags_lower for t in ("soundfont", "sf2", "sf3"))


def _github_query(query: str) -> str:
    terms = ["topic:soundfont"]
    if query:
        terms.append(query)
        terms.append("in:name,description,readme")
    return " ".join(terms)


def _safe_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

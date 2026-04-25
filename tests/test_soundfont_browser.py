"""Tests for app.core.soundfont_browser — mocks HTTP, no network calls."""
from __future__ import annotations

import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.soundfont_browser import (
    BrowserError,
    MusicalArtifactsProvider,
    SoundFontResult,
    download_to_library,
)


def _fake_response(json_data=None, status_code=200, content=b"", headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.content = content
    resp.headers = headers or {}
    if status_code >= 400:
        from requests.exceptions import HTTPError
        resp.raise_for_status.side_effect = HTTPError(f"HTTP {status_code}")
    else:
        resp.raise_for_status.return_value = None
    # iter_content yields one chunk
    resp.iter_content = lambda chunk_size=65536: iter([content]) if content else iter([])
    return resp


def _ma_artifact(**overrides):
    base = {
        "id": 1234,
        "name": "Test SoundFont",
        "author": "Tester",
        "description": "An sf2 used for tests.",
        "license": "CC-BY-4.0",
        "file": "https://files.example.com/test.sf2",
        "file_size": 5_242_880,
        "tags": ["soundfont", "piano"],
        "download_count": 42,
        "url": "https://musical-artifacts.com/artifacts/1234",
        "file_hash": "deadbeef",
    }
    base.update(overrides)
    return base


def test_provider_search_parses_response():
    payload = [_ma_artifact(), _ma_artifact(id=2, name="Second", file="https://x/y.sf2")]
    session = MagicMock()
    session.headers = {}
    session.get.return_value = _fake_response(json_data=payload)

    provider = MusicalArtifactsProvider(session=session)
    results = provider.search("piano")

    assert len(results) == 2
    r = results[0]
    assert isinstance(r, SoundFontResult)
    assert r.source == "musical-artifacts.com"
    assert r.name == "Test SoundFont"
    assert r.author == "Tester"
    assert r.license == "CC-BY-4.0"
    assert r.file_size_bytes == 5_242_880
    assert "piano" in r.tags
    assert r.download_count == 42


def test_provider_search_filters_non_soundfont_files():
    payload = [
        _ma_artifact(file="https://x/sample.wav", tags=["sample"]),  # should be filtered
        _ma_artifact(file="https://x/foo.sf2", tags=["soundfont"]),
    ]
    session = MagicMock()
    session.headers = {}
    session.get.return_value = _fake_response(json_data=payload)

    provider = MusicalArtifactsProvider(session=session)
    results = provider.search()
    assert len(results) == 1
    assert results[0].file_url.endswith(".sf2")


def test_provider_search_keeps_zip_with_soundfont_tag():
    payload = [_ma_artifact(file="https://x/bundle.zip", tags=["soundfont"])]
    session = MagicMock()
    session.headers = {}
    session.get.return_value = _fake_response(json_data=payload)

    provider = MusicalArtifactsProvider(session=session)
    results = provider.search()
    assert len(results) == 1
    assert results[0].file_url.endswith(".zip")


def test_provider_search_passes_tag_soundfont():
    session = MagicMock()
    session.headers = {}
    session.get.return_value = _fake_response(json_data=[])

    provider = MusicalArtifactsProvider(session=session)
    provider.search("query")

    _, kwargs = session.get.call_args
    assert kwargs["params"]["tag"] == "soundfont"
    assert kwargs["params"]["q"] == "query"


def test_provider_handles_dict_tag_shape():
    payload = [_ma_artifact(tags=[{"name": "soundfont"}, {"name": "orchestral"}])]
    session = MagicMock()
    session.headers = {}
    session.get.return_value = _fake_response(json_data=payload)

    provider = MusicalArtifactsProvider(session=session)
    results = provider.search()
    assert "soundfont" in results[0].tags
    assert "orchestral" in results[0].tags


def test_provider_raises_on_http_error():
    session = MagicMock()
    session.headers = {}
    session.get.return_value = _fake_response(status_code=500)

    provider = MusicalArtifactsProvider(session=session)
    with pytest.raises(BrowserError):
        provider.search()


def test_provider_raises_on_non_json_response():
    session = MagicMock()
    session.headers = {}
    resp = _fake_response()
    resp.json.side_effect = ValueError("not json")
    session.get.return_value = resp

    provider = MusicalArtifactsProvider(session=session)
    with pytest.raises(BrowserError):
        provider.search()


def test_provider_caches_to_disk(tmp_path):
    payload = [_ma_artifact()]
    session = MagicMock()
    session.headers = {}
    session.get.return_value = _fake_response(json_data=payload)

    provider = MusicalArtifactsProvider(session=session, cache_dir=tmp_path / "cache")
    r1 = provider.search("piano")
    r2 = provider.search("piano")  # second call should hit cache, not session
    assert r1 == r2
    assert session.get.call_count == 1  # cache hit on the second call


def _valid_sf2_bytes() -> bytes:
    """Smallest byte sequence that passes our RIFF/sfbk validation."""
    return b"RIFF" + struct.pack("<I", 4) + b"sfbk" + b"\x00" * 32


def test_download_writes_validated_sf2(tmp_path):
    sf2_bytes = _valid_sf2_bytes()
    session = MagicMock()
    session.headers = {}
    session.get.return_value = _fake_response(content=sf2_bytes, headers={"Content-Length": str(len(sf2_bytes))})

    result = SoundFontResult(
        source="musical-artifacts.com",
        name="Tester",
        author="Author",
        description="",
        license="CC0",
        file_url="https://files.example.com/test.sf2",
        file_size_bytes=len(sf2_bytes),
        tags=("soundfont",),
        download_count=1,
        detail_url="https://musical-artifacts.com/artifacts/1",
    )

    path = download_to_library(result, tmp_path / "lib", session=session)
    assert path.exists()
    assert path.suffix == ".sf2"
    assert path.read_bytes() == sf2_bytes


def test_download_rejects_invalid_sf2(tmp_path):
    bad_bytes = b"NOT A SOUNDFONT FILE"
    session = MagicMock()
    session.headers = {}
    session.get.return_value = _fake_response(content=bad_bytes)

    result = SoundFontResult(
        source="musical-artifacts.com",
        name="Bad",
        author=None,
        description="",
        license="Unknown",
        file_url="https://x/bad.sf2",
        file_size_bytes=len(bad_bytes),
        tags=("soundfont",),
        download_count=0,
        detail_url="",
    )

    with pytest.raises(BrowserError, match="validation"):
        download_to_library(result, tmp_path / "lib", session=session)


def test_download_respects_cancel(tmp_path):
    sf2_bytes = _valid_sf2_bytes() * 10
    session = MagicMock()
    session.headers = {}
    resp = _fake_response(content=sf2_bytes)
    # Yield in 4 chunks so cancel can fire mid-stream
    chunks = [sf2_bytes[i : i + len(sf2_bytes) // 4] for i in range(0, len(sf2_bytes), max(1, len(sf2_bytes) // 4))]
    resp.iter_content = lambda chunk_size=65536: iter(chunks)
    session.get.return_value = resp

    result = SoundFontResult(
        source="musical-artifacts.com",
        name="Long",
        author=None,
        description="",
        license="CC0",
        file_url="https://x/long.sf2",
        file_size_bytes=None,
        tags=("soundfont",),
        download_count=0,
        detail_url="",
    )

    state = {"called": 0}

    def cancel():
        state["called"] += 1
        return state["called"] > 1  # cancel after first chunk

    with pytest.raises(BrowserError, match="cancel"):
        download_to_library(result, tmp_path / "lib", session=session, cancel_check=cancel)


def test_download_handles_name_collision(tmp_path):
    sf2_bytes = _valid_sf2_bytes()
    session = MagicMock()
    session.headers = {}
    # Same response served for both downloads
    session.get.side_effect = [
        _fake_response(content=sf2_bytes),
        _fake_response(content=sf2_bytes),
    ]

    result = SoundFontResult(
        source="musical-artifacts.com",
        name="Same",
        author=None,
        description="",
        license="CC0",
        file_url="https://x/same.sf2",
        file_size_bytes=len(sf2_bytes),
        tags=("soundfont",),
        download_count=0,
        detail_url="",
    )

    p1 = download_to_library(result, tmp_path / "lib", session=session)
    p2 = download_to_library(result, tmp_path / "lib", session=session)
    assert p1 != p2
    assert p1.exists() and p2.exists()


def test_safe_int_handles_garbage():
    from app.core.soundfont_browser import _safe_int
    assert _safe_int(None) is None
    assert _safe_int("abc") is None
    assert _safe_int("42") == 42
    assert _safe_int(7) == 7

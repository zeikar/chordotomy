import hashlib
import http.client
import os
import urllib.error
from pathlib import Path

import pytest

from chordotomy import beats
from chordotomy.model import EngineError

PAYLOAD = b"not really weights" * 1000


class FakeResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def read(self, n: int) -> bytes:
        chunk = self.data[self.pos : self.pos + n]
        self.pos += len(chunk)
        return chunk


@pytest.fixture
def cache(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(beats, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(
        beats, "CHECKPOINTS", {"final0": (hashlib.sha256(PAYLOAD).hexdigest(), len(PAYLOAD))}
    )
    return tmp_path / "cache"


def serve(monkeypatch, data: bytes = PAYLOAD) -> list[str]:
    calls = []

    def opener(url, timeout):
        calls.append(url)
        return FakeResponse(data)

    monkeypatch.setattr(beats, "urlopen", opener)
    return calls


def test_cache_dir_honours_xdg_cache_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(beats, "CACHE_DIR", None)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    assert beats.cache_dir() == tmp_path / "chordotomy"


@pytest.mark.parametrize("xdg", [None, ""])
def test_cache_dir_falls_back_to_the_home_cache(monkeypatch, tmp_path, xdg) -> None:
    monkeypatch.setattr(beats, "CACHE_DIR", None)
    monkeypatch.setenv("HOME", str(tmp_path))
    if xdg is None:
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    else:
        monkeypatch.setenv("XDG_CACHE_HOME", xdg)

    assert beats.cache_dir() == tmp_path / ".cache" / "chordotomy"


def test_fetch_downloads_once_and_verifies(cache, monkeypatch) -> None:
    calls = serve(monkeypatch)
    assert not beats.verified()

    path = beats.fetch()

    assert path == cache / "beat_this-final0.ckpt"
    assert path.read_bytes() == PAYLOAD
    assert beats.verified()
    assert list(cache.iterdir()) == [path]
    assert calls == [f"{beats.CHECKPOINT_URL}/final0.ckpt"]

    monkeypatch.setattr(beats, "urlopen", lambda *a, **k: pytest.fail("downloaded twice"))
    assert beats.fetch() == path


def test_a_damaged_file_is_replaced(cache, monkeypatch) -> None:
    cache.mkdir()
    (cache / "beat_this-final0.ckpt").write_bytes(b"other bytes")
    calls = serve(monkeypatch)
    assert not beats.verified()

    path = beats.fetch()

    assert len(calls) == 1
    assert path.read_bytes() == PAYLOAD


@pytest.mark.parametrize(
    ("data", "wrong"),
    [(b"x" * len(PAYLOAD), "SHA-256"), (PAYLOAD[:-1], "not the pinned")],
    ids=["digest", "size"],
)
def test_a_download_failing_the_pin_is_not_kept(cache, monkeypatch, data, wrong) -> None:
    serve(monkeypatch, data)

    with pytest.raises(EngineError, match=wrong):
        beats.fetch()

    assert list(cache.iterdir()) == []


def test_a_cut_connection_is_an_engine_error(cache, monkeypatch) -> None:
    class Cut(FakeResponse):
        def read(self, n: int) -> bytes:
            if self.pos:
                raise http.client.IncompleteRead(b"")
            self.pos = 1
            return PAYLOAD[:10]

    monkeypatch.setattr(beats, "urlopen", lambda url, timeout: Cut(PAYLOAD))

    with pytest.raises(EngineError) as info:
        beats.fetch()

    assert beats.CHECKPOINT_URL in str(info.value)
    assert "fetch-weights" in str(info.value)
    assert list(cache.iterdir()) == []


def test_an_offline_fetch_says_what_to_do(cache, monkeypatch) -> None:
    def offline(url, timeout):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(beats, "urlopen", offline)

    with pytest.raises(EngineError) as info:
        beats.fetch()

    message = str(info.value)
    for part in (beats.CHECKPOINT_URL, str(cache), "fetch-weights", "--engine dsp"):
        assert part in message
    assert list(cache.iterdir()) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_an_unwritable_cache_is_an_engine_error(cache, monkeypatch, tmp_path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o500)
    monkeypatch.setattr(beats, "CACHE_DIR", locked)
    serve(monkeypatch)

    try:
        with pytest.raises(EngineError, match=str(locked)):
            beats.fetch()
    finally:
        locked.chmod(0o700)

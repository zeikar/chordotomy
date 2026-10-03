import hashlib
import http.client
import math
import os
import sys
import types
import urllib.error
from pathlib import Path

import numpy as np
import pytest

from chordotomy import beats
from chordotomy.features import HOP, SR, NoBeatsError
from chordotomy.model import EngineError

PAYLOAD = b"not really weights" * 1000
# Bound at import, before conftest's dsp_engine replaces it in each test.
REAL_ACTIVATION = beats.activation


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


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read anything")
def test_an_unreadable_file_is_replaced(cache, monkeypatch) -> None:
    # As a root-owned file left by a sudo fetch-weights: the right bytes, not the user's to read.
    cache.mkdir()
    unreadable = cache / "beat_this-final0.ckpt"
    unreadable.write_bytes(PAYLOAD)
    unreadable.chmod(0)
    calls = serve(monkeypatch)
    assert not beats.verified()

    path = beats.fetch()

    assert len(calls) == 1
    assert path.read_bytes() == PAYLOAD
    assert beats.verified()


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


@pytest.mark.parametrize("n", [1, 512])
def test_a_clip_too_short_for_the_spectrogram_has_no_beats(synth, monkeypatch, n) -> None:
    class Fake(types.ModuleType):
        def __getattr__(self, name):
            raise AssertionError(f"{self.__name__}.{name} used before the length check")

    for name in ("torch", "beat_this"):
        monkeypatch.setitem(sys.modules, name, Fake(name))

    with pytest.raises(NoBeatsError):
        REAL_ACTIVATION(synth([("C:maj", 8)])[:n])


@pytest.mark.parametrize(
    ("values", "found"),
    [
        ([-3.0, -0.5, 0.2, -1.0], True),
        ([-3.0, -0.5, -1.0], False),
        ([0.0, 0.0], False),
        ([], False),
    ],
    ids=["one-positive", "all-negative", "all-zero", "empty"],
)
def test_has_peaks_is_any_logit_above_zero(values, found) -> None:
    assert beats.has_peaks(np.array(values, dtype=np.float32)) is found


def test_resample_lands_on_the_hop_frames() -> None:
    n_frames = 1 + 3 * SR // HOP
    spike = np.zeros(3 * beats.FPS + 1)
    spike[beats.FPS] = 1.0  # t = 1.0 s

    assert len(beats.resample(spike, n_frames)) == n_frames
    np.testing.assert_allclose(beats.resample(np.full(len(spike), 0.25), n_frames), 0.25)
    assert beats.resample(spike, n_frames).argmax() == round(1.0 * SR / HOP)


BORDER = beats.BORDER_FRAMES
STEP = beats.CHUNK_FRAMES - 2 * BORDER


@pytest.mark.parametrize("n", [1, STEP - 1, STEP, STEP + 1, 2 * beats.CHUNK_FRAMES + 1])
def test_chunking_keeps_every_frame_once_from_the_first_chunk_holding_it(n) -> None:
    # Each frame's index + 1 in its first bin, so a zero-padded row reads as -1.
    spect = np.zeros((n, beats.N_MELS), dtype=np.float32)
    spect[:, 0] = np.arange(n) + 1
    lengths = []
    spans = []  # the first and end frame of each chunk's kept output

    def index(chunk: np.ndarray) -> np.ndarray:
        lengths.append(len(chunk))
        return chunk[:, 0] - 1

    def owner(chunk: np.ndarray) -> np.ndarray:
        kept = chunk[BORDER:-BORDER, 0] - 1
        spans.append((kept[0], kept[-1] + 1))
        return np.full(len(chunk), kept[0])

    frames = beats._chunked(spect, index)
    owners = beats._chunked(spect, owner)

    np.testing.assert_array_equal(frames, np.arange(n))
    assert len(lengths) == math.ceil(n / STEP)
    # Padded by BORDER at both ends when the piece fits one chunk's kept span; else every chunk
    # is full, the last one ending at the piece's end (split_piece's avoid_short_end).
    assert lengths == ([n + 2 * BORDER] if n <= STEP else [beats.CHUNK_FRAMES] * len(lengths))
    # Where kept spans overlap, the earlier chunk's stays (aggregate_prediction's keep_first).
    first = [min(start for start, end in spans if start <= f < end) for f in range(n)]
    np.testing.assert_array_equal(owners, first)

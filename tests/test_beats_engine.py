"""Beat This!'s activation on the real net; skipped unless the model extra and its weights are here.

The suite never downloads: `chordotomy fetch-weights` puts the checkpoint in the cache first.
"""

import contextlib
import hashlib
import importlib.util

import numpy as np
import pytest
import soundfile
from test_timeline import CYCLE, _matched, _two_beat_chords, _write

from chordotomy import beats, features, model
from chordotomy.features import HOP, SR, NoBeatsError
from chordotomy.model import EngineError
from chordotomy.timeline import analyze

# find_spec rather than importorskip: collecting the file then imports neither beat_this nor torch.
if importlib.util.find_spec("beat_this") is None or not beats.verified():
    pytest.skip(
        "the model extra or the Beat This! weights are not installed", allow_module_level=True
    )

# Bound at import, before conftest's stubs replace them in each test.
REAL_AVAILABLE = model.available
REAL_ACTIVATION = beats.activation


@pytest.fixture(autouse=True)
def beat_this_engine(monkeypatch):
    """Undo conftest's stubs, and fail any download."""
    monkeypatch.setattr(model, "available", REAL_AVAILABLE)
    monkeypatch.setattr(beats, "activation", REAL_ACTIVATION)
    monkeypatch.setattr(beats, "urlopen", lambda *a, **k: pytest.fail("the suite downloaded"))


@pytest.fixture
def fresh_tracker():
    """Load the net anew in the test, and again after it, so a patched load does not stick."""
    beats._tracker.cache_clear()
    yield
    beats._tracker.cache_clear()


def _picked(logits: np.ndarray) -> bool:
    """Whether Beat This!'s own peak picking, Postprocessor("minimal"), finds a beat."""
    import torch
    from beat_this.model.postprocessor import Postprocessor

    beat = torch.from_numpy(np.ascontiguousarray(logits, dtype=np.float32))
    found, _ = Postprocessor("minimal")(beat, beat)
    return len(found) > 0


def test_the_spectrogram_matches_beat_this(mix) -> None:
    pytest.importorskip("torchaudio")
    import torch
    from beat_this.preprocessing import LogMelSpect

    y = mix([("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:7", 4), ("C:maj", 4)])  # 10 s

    mel = beats._log_mel(y)

    ref = LogMelSpect()(torch.from_numpy(y)).numpy()
    assert mel.shape == ref.shape == (1 + len(y) // beats.MEL_HOP, beats.N_MELS)
    # Measured: 1.9e-5, on values up to 6.8.
    assert np.abs(mel - ref).max() < 1e-3


@pytest.mark.parametrize(("clip", "found"), [("syncopated", True), ("silence", False)])
def test_the_gate_agrees_with_beat_this_peak_picking(syncopated, clip, found) -> None:
    y = syncopated(8, 8, 86) if clip == "syncopated" else np.zeros(4 * SR, dtype=np.float32)

    logits = beats.logits(y)

    assert beats.has_peaks(logits) is found
    assert _picked(logits) is found


def test_the_shortest_clip_the_spectrogram_takes_runs(synth) -> None:
    # The first length that reaches torch.stft: beats or none, never its RuntimeError.
    y = synth([("C:maj", 8)])[: beats.N_FFT // 2 + 1]

    with contextlib.suppress(NoBeatsError):
        assert beats.activation(y).shape == (1 + len(y) // HOP,)


@pytest.mark.parametrize("length", [beats.N_FFT // 2 + 1, 1024])
# The DSP's onset strength warns that its window is longer than the clip, which is the point here.
@pytest.mark.filterwarnings("ignore:n_fft=2048 is too large:UserWarning")
def test_a_clip_too_short_for_a_beat_has_none_on_either_engine(synth, tmp_path, length) -> None:
    # The shortest clip the spectrogram takes and the longest the DSP finds no beat in: both
    # engines say "no beats" and nothing else. Measured: on the model engine it is Beat This!'s
    # gate, every logit below 0.
    path = tmp_path / "clip.wav"
    soundfile.write(path, synth([("C:maj", 8)])[:length], SR)

    for engine in ("dsp", "model"):
        with pytest.raises(NoBeatsError):
            analyze(path, engine=engine)


def test_digital_silence_has_no_beats(tmp_path) -> None:
    silence = np.zeros(4 * SR, dtype=np.float32)

    with pytest.raises(NoBeatsError):
        beats.activation(silence)
    with pytest.raises(NoBeatsError):
        analyze(_write(tmp_path, silence), engine="model")


def test_the_gate_agrees_at_its_edge(synth) -> None:
    # One strike per bar of 4 beats at 90 BPM, held: a few frames stand far above the rest.
    y = synth([(CYCLE[i % len(CYCLE)], 1) for i in range(12)], bpm=90 / 4, decay=2.0)
    logits = beats.logits(y)

    for above in (0, 1, 3):
        # Shifted so that exactly `above` frames stay above 0.
        shifted = logits - np.sort(logits)[-1 - above]
        assert np.sum(shifted > 0) == above
        assert beats.has_peaks(shifted) is _picked(shifted) is (above > 0), above


@pytest.mark.parametrize("length", [4 * SR + 1, 5 * SR + 300, 6 * SR + 511])
def test_the_activation_has_the_frames_of_the_beat_grid(drums, length) -> None:
    activation = beats.activation(drums(16)[:length])

    assert activation.shape == (1 + length // HOP,)
    assert activation.dtype == np.float64
    assert activation.min() >= 0
    assert activation.max() <= 1


def test_logits_are_chunked_as_beat_this_chunks_them(mix, monkeypatch) -> None:
    pytest.importorskip("torchaudio")
    import torch
    from beat_this.inference import split_predict_aggregate

    y = mix([("C:maj", 6), ("A:min", 6), ("F:maj", 6), ("G:7", 6)])  # 12 s, 601 frames
    # Three chunks, the last one moved back to end at the piece's end, overlapping the second.
    monkeypatch.setattr(beats, "CHUNK_FRAMES", 300)

    logits = beats.logits(y)

    with torch.inference_mode():
        ref = split_predict_aggregate(
            torch.from_numpy(beats._log_mel(y)),
            chunk_size=300,
            border_size=beats.BORDER_FRAMES,
            overlap_mode="keep_first",
            model=beats._tracker(beats.CHECKPOINT),
        )["beat"].numpy()
    # Measured: 0.0. Compared with the default chunks instead, the logits differ by up to 6.8 on
    # nearly every frame: the transformer attends over its whole chunk, so the context changes
    # each frame's output, not only the borders'. Hence the reference is beat_this's own chunking.
    np.testing.assert_allclose(logits, ref, atol=1e-4)


def test_the_net_runs_on_the_cpu_even_when_cuda_is_reported(
    drums, monkeypatch, fresh_tracker
) -> None:
    monkeypatch.setattr("torch.cuda.device_count", lambda: 1)

    beats.activation(drums(8))

    net = beats._tracker(beats.CHECKPOINT)
    assert {t.device.type for t in [*net.parameters(), *net.buffers()]} == {"cpu"}


def test_a_checkpoint_that_cannot_be_loaded_is_an_engine_error(
    drums, tmp_path, monkeypatch, fresh_tracker
) -> None:
    garbage = b"not a checkpoint" * 64
    monkeypatch.setattr(beats, "CACHE_DIR", tmp_path)
    # Pinned to the garbage itself, so fetch takes it as verified rather than downloading.
    pin = (hashlib.sha256(garbage).hexdigest(), len(garbage))
    monkeypatch.setattr(beats, "CHECKPOINTS", {beats.CHECKPOINT: pin})
    beats.checkpoint_path().write_bytes(garbage)

    with pytest.raises(EngineError) as info:
        beats.activation(drums(8))

    message = str(info.value)
    for part in (str(beats.checkpoint_path()), "--reinstall-package beat-this", "--engine dsp"):
        assert part in message
    assert "\n" not in message


def test_a_constant_tempo_keeps_the_global_grid(synth, tmp_path) -> None:
    y, strikes, struck = _two_beat_chords(synth, 120, 48)

    result = analyze(_write(tmp_path, y), engine="model")

    hit, _ = _matched(result, strikes, struck)
    # Measured: all 96 strikes hit, on 97 beats.
    assert hit >= 0.95, hit
    # The octave check's negative case on this engine too.
    assert abs(len(result["beats"]) - len(strikes)) <= 2, (len(result["beats"]), len(strikes))


def test_a_syncopated_constant_tempo_keeps_the_global_grid(synth, syncopated, tmp_path) -> None:
    # 86 BPM throughout: 8 bars of hats on the eighths, then 8 of syncopated hats.
    chords, strikes, struck = _two_beat_chords(synth, 86, 32)
    y = chords + syncopated(8, 8, 86)
    y = y / np.abs(y).max() * 0.5

    result = analyze(_write(tmp_path, y), engine="model")

    hit, _ = _matched(result, strikes, struck)
    gaps = np.diff(result["beats"])
    # Measured: all 64 strikes hit; 65 beats of 0.674 to 0.720 s, a ratio of 1.07.
    # Beat This!'s own peaks give 2.04, which is why the DP is kept.
    assert hit >= 0.95, hit
    assert gaps.max() < 1.2 * gaps.min(), (gaps.min(), gaps.max())


def test_a_half_tempo_lock_is_doubled(half_locked, tmp_path, monkeypatch) -> None:
    y, strikes, struck = _two_beat_chords(half_locked, 180, 36)
    path = _write(tmp_path, y)

    hit, correct = _matched(analyze(path, engine="model"), strikes, struck)

    # Measured: 71 of 72 strikes hit, on a median beat of 0.325 s, and every matched beat carries
    # the chord struck on it.
    assert hit >= 0.9, hit
    assert correct >= 0.9, correct

    monkeypatch.setattr(features, "OCTAVE_MIN_CHANGES", 10_000)
    hit, _ = _matched(analyze(path, engine="model"), strikes, struck)

    # Measured with the check off: 36 beats, 50 % of the strikes hit and 83 % of the matched beats
    # carry their chord. Beat This! half-locks this fixture too, so the octave
    # check is still what doubles it.
    assert hit <= 0.6, hit


def test_held_chords_keep_a_steady_grid(synth, tmp_path) -> None:
    # One strike per bar of 4 beats at 90 BPM, held: 48 beats.
    y = synth([(CYCLE[i % len(CYCLE)], 1) for i in range(12)], bpm=90 / 4, decay=2.0)

    result = analyze(_write(tmp_path, y), engine="model")

    gaps = np.diff(result["beats"])
    # Measured: 49 beats of 0.604 to 0.697 s, a ratio of 1.15. Beat This!'s own peaks leave gaps up
    # to 1.84 s here; the DP must not.
    assert abs(len(result["beats"]) - 48) <= 4, len(result["beats"])
    assert gaps.max() < 1.2 * gaps.min(), (gaps.min(), gaps.max())

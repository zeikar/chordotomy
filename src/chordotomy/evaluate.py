"""Real-audio evaluation: score a timeline against reference chords with mir_eval.

Opt-in, for development only. It needs the `eval` extra (mir_eval, pooch), which is imported inside
the functions that use it so that importing this module works without it. Nothing here reaches
the timeline JSON or the `analyze` command.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Literal, NamedTuple

import numpy as np

from . import timeline
from .chords import ROOTS

METRICS = ("root", "majmin", "sevenths", "tetrads", "majmin_inv")

# mir_eval's default, passed explicitly so both datasets trim the same. A median GuitarSet take
# loses about 17 % of its length to it, the same for every run.
BEAT_MIN_TIME = 5.0

# Scale degree of the bass above the chord root, by semitone offset 1..11, as mir_eval reads it.
DEGREES = ("b2", "2", "b3", "3", "4", "b5", "5", "b6", "6", "b7", "7")

# Both datasets are CC BY 4.0 (Zenodo). They are downloaded on demand into cache_dir() and never
# committed (in a checkout that is the gitignored datasets/).
REGISTRY = {
    "tinyAAM.zip": "md5:9121d5ae106747e67721bde0d55f9e00",
    "annotation.zip": "md5:b39b78e63d3446f2e54ddb7a54df9b10",
    "audio_mono-mic.zip": "md5:275966d6610ac34999b58426beb119c3",
}
URLS = {
    "tinyAAM.zip": "https://zenodo.org/api/records/6771120/files/tinyAAM.zip/content",
    "annotation.zip": "https://zenodo.org/api/records/3371780/files/annotation.zip/content",
    "audio_mono-mic.zip": "https://zenodo.org/api/records/3371780/files/audio_mono-mic.zip/content",
}
TINY_AAM_IDS = [
    "0001",
    "0080",
    "0192",
    "0620",
    "0758",
    "0989",
    "1014",
    "1050",
    "1545",
    "1711",
    "1941",
    "2269",
    "2395",
    "2462",
    "2602",
    "2720",
    "2828",
    "2841",
    "2990",
    "3000",
]
# None means cache_dir() decides; tests point it at a temporary directory.
CACHE_DIR: Path | None = None
_CHECKOUT = Path(__file__).resolve().parents[2]

_AAM_CHORD = re.compile(r"([A-G]#?)(maj|min)")


def timeline_to_intervals(result: dict) -> tuple[np.ndarray, list[str]]:
    """Intervals and mir_eval labels of a timeline's segments; a bass off the root is a slash."""
    intervals = []
    labels = []
    for s in result["segments"]:
        label = s["chord"]
        if label != "N" and s["bass"] is not None:
            root = label.split(":")[0]
            offset = (ROOTS.index(s["bass"]) - ROOTS.index(root)) % 12
            if offset:
                label = f"{label}/{DEGREES[offset - 1]}"
        intervals.append((s["start_time"], s["end_time"]))
        labels.append(label)
    return np.array(intervals, dtype=float).reshape(-1, 2), labels


def bass_missing(result: dict) -> list[bool]:
    """Per segment: a chord was labeled but no bass was detected for it."""
    return [s["chord"] != "N" and s["bass"] is None for s in result["segments"]]


class Reference(NamedTuple):
    """A track's reference chords, and its annotated beat times in seconds."""

    intervals: np.ndarray
    labels: list[str]
    beats: np.ndarray


def tiny_aam_reference(text: str, duration: float) -> Reference:
    """Beat-level reference from a Tiny AAM beatinfo.arff; each beat ends where the next starts."""
    starts = []
    labels = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] in "@%":
            continue
        start, _bar, _quarter, name = line.split(",", 3)
        name = name.strip().strip("'")
        if name == "N.C.":
            label = "N"
        elif match := _AAM_CHORD.fullmatch(name):
            label = f"{match[1]}:{match[2]}"
        else:
            raise ValueError(f"unsupported chord label {name!r}")
        starts.append(float(start))
        labels.append(label)
    # The annotation stops at the last played beat. Stretching that beat over the silent tail
    # would reward calling the tail a chord, so it lasts as long as the gap before it (a median
    # would misjudge a final tempo change) and the rest is N.
    end = duration
    if len(starts) > 1:
        end = min(starts[-1] + (starts[-1] - starts[-2]), duration)
    intervals = np.column_stack([starts, [*starts[1:], end]]).astype(float)
    if end < duration:
        intervals = np.vstack([intervals, [end, duration]])
        labels.append("N")
    return Reference(intervals, labels, np.array(starts, dtype=float))


def guitarset_reference(jams: dict) -> Reference:
    """The performed chord annotation of a GuitarSet JAMS dict (it carries the bass)."""
    performed = [
        a
        for a in jams["annotations"]
        if a["namespace"] == "chord"
        and a["annotation_metadata"]["data_source"].startswith("Semi-automatic")
    ]
    if len(performed) != 1:
        raise ValueError(f"expected one Semi-automatic chord annotation, found {len(performed)}")
    beats = [a for a in jams["annotations"] if a["namespace"] == "beat_position"]
    if len(beats) != 1:
        raise ValueError(f"expected one beat_position annotation, found {len(beats)}")
    data = performed[0]["data"]
    intervals = np.array([(d["time"], d["time"] + d["duration"]) for d in data], dtype=float)
    times = np.array([d["time"] for d in beats[0]["data"]], dtype=float)
    return Reference(intervals, [d["value"] for d in data], times)


def beat_metrics(ref_beats: np.ndarray, est_beats: np.ndarray) -> dict:
    """Beat F-measure, CMLt and AMLt of the estimated grid, and its period over the reference's."""
    import mir_eval

    ratio = float("nan")
    if len(ref_beats) > 1 and len(est_beats) > 1:
        ratio = float(np.median(np.diff(est_beats)) / np.median(np.diff(ref_beats)))
    # A clip that ends before BEAT_MIN_TIME leaves no reference beat to score against: mir_eval
    # would warn and score 0, a miss the overall row would count.
    if len(mir_eval.beat.trim_beats(ref_beats, BEAT_MIN_TIME)) < 2:
        nan = float("nan")
        return {"beat_f": nan, "cmlt": nan, "amlt": nan, "period_ratio": ratio}
    scores = mir_eval.beat.evaluate(ref_beats, est_beats, min_beat_time=BEAT_MIN_TIME)
    return {
        "beat_f": scores["F-measure"],
        "cmlt": scores["Correct Metric Level Total"],
        "amlt": scores["Any Metric Level Total"],
        "period_ratio": ratio,
    }


def score(
    ref_intervals: np.ndarray,
    ref_labels: list[str],
    est_intervals: np.ndarray,
    est_labels: list[str],
    est_bass_missing: list[bool] | None = None,
) -> dict:
    """One track's per-interval comparisons and durations for each metric, plus the N shares.

    n_est and n_ref are the shares of the duration labeled N; n_hit is the share where both are.

    est_bass_missing flags estimate segments whose chord has no detected bass. A bare `C:maj`
    reads as root position to mir_eval, which would award an inversion the estimate never
    showed, so majmin_inv counts such a span as a miss whatever the reference bass. The other
    metrics ignore the flag.
    """
    import mir_eval

    if est_bass_missing is None:
        est_bass_missing = [False] * len(est_labels)
    # The flag rides along with each label through padding and merging as a (label, flag) pair.
    est_intervals, paired = mir_eval.util.adjust_intervals(
        est_intervals,
        list(zip(est_labels, est_bass_missing, strict=True)),
        ref_intervals.min(),
        ref_intervals.max(),
        ("N", False),
        ("N", False),
    )
    intervals, ref, paired = mir_eval.util.merge_labeled_intervals(
        ref_intervals, ref_labels, est_intervals, paired
    )
    est = [label for label, _ in paired]
    durations = mir_eval.util.intervals_to_durations(intervals)
    total = float(durations.sum())
    track = {metric: (getattr(mir_eval.chord, metric)(ref, est), durations) for metric in METRICS}
    inv = track["majmin_inv"][0]
    for i, (_, missing) in enumerate(paired):
        # -1 is an interval mir_eval excluded; it stays excluded.
        if missing and inv[i] != -1:
            inv[i] = 0.0
    est_n = np.array(est) == "N"
    ref_n = np.array(ref) == "N"
    track["n_est"] = float(durations[est_n].sum()) / total
    track["n_ref"] = float(durations[ref_n].sum()) / total
    track["n_hit"] = float(durations[est_n & ref_n].sum()) / total
    track["duration"] = total
    return track


def _reference_chord(label: str) -> tuple[int, int, set[int]]:
    """Root, bass degree and chord-tone degrees of a reference label; root -1 for N or X.

    The tones are encode's bitmap before it adds the bass, so a slash off the chord (C:maj/2)
    leaves its bass outside them.
    """
    import mir_eval

    root, quality, extensions, bass = mir_eval.chord.split(label)
    if root in (mir_eval.chord.NO_CHORD, mir_eval.chord.X_CHORD):
        return -1, 0, set()
    tones = mir_eval.chord.quality_to_bitmap(quality)
    tones[0] = 1
    for degree in extensions:
        tones = tones + mir_eval.chord.scale_degree_to_bitmap(degree, False)
    return (
        mir_eval.chord.pitch_class_to_semitone(root),
        mir_eval.chord.scale_degree_to_semitone(bass) % 12,
        {int(i) for i in np.flatnonzero(tones > 0)},
    )


def bass_metrics(result: dict, reference: Reference) -> dict:
    """One track's bass columns: (hit, denominator) durations for bass_ref, inv_prec, inv_rec.

    Scored per beat, each lasting until the next beat (the last until the source's end), against
    the reference interval holding its midpoint; no interval, an N or an X, is a reference N. A
    reference annotation without a bass (Tiny AAM) reads as root position.

    bass_ref counts the beats where the estimate is a chord and the reference is too, a hit when
    the written bass is the reference's. An inversion is a bass off the root and on a chord tone.
    inv_prec counts the estimate's inversion beats and inv_rec the reference's, an estimate N or
    bass-less beat among them a miss; a hit is both inverted over the same bass. nonchord is the
    share of the duration in segments whose bass is outside their chord.
    """
    beats = result["beats"]
    duration = result["source"]["duration"]
    segments = result["segments"]
    bounds = [*beats[1:], duration]
    mids = (np.array(beats) + np.array(bounds)) / 2
    spans = reference.intervals
    found = np.searchsorted(spans[:, 0], mids, side="right") - 1

    sums = {key: [0.0, 0.0] for key in ("bass_ref", "inv_prec", "inv_rec")}
    segment = iter(segments)
    current = next(segment)
    for i, (start, end) in enumerate(zip(beats, bounds, strict=True)):
        while current["end_beat"] <= i:
            current = next(segment)
        length = end - start

        chord, bass = current["chord"], current["bass"]
        est_inverted = current["inversion"] in ("first", "second", "third")

        ref_root, ref_degree, ref_tones = -1, 0, set()
        if found[i] >= 0 and mids[i] < spans[found[i], 1]:
            ref_root, ref_degree, ref_tones = _reference_chord(reference.labels[found[i]])
        ref_bass = ROOTS[(ref_root + ref_degree) % 12] if ref_root >= 0 else None
        ref_inverted = ref_degree != 0 and ref_degree in ref_tones
        same = est_inverted and ref_inverted and bass == ref_bass

        if chord != "N" and ref_root >= 0:
            sums["bass_ref"][1] += length
            sums["bass_ref"][0] += length * (bass == ref_bass)
        if est_inverted:
            sums["inv_prec"][1] += length
            sums["inv_prec"][0] += length * same
        if ref_inverted:
            sums["inv_rec"][1] += length
            sums["inv_rec"][0] += length * same
    off_chord = sum(
        s["end_time"] - s["start_time"] for s in segments if s["inversion"] == "non_chord"
    )
    return {**{key: tuple(pair) for key, pair in sums.items()}, "nonchord": off_chord / duration}


def summarise(tracks: dict[str, dict]) -> dict[str, dict]:
    """Accuracy, N, beat and bass rates per track, plus an `overall` row weighted by duration.

    The bass ratios (bass_ref, inv_prec, inv_rec) are the exception: their overall is the summed
    hits over the summed denominators, so a track weighs by what it adds to that metric.

    N precision is the share of estimated N that is reference N, and N recall the share of
    reference N estimated as N (nan when there is none). The period ratio's overall is the
    median over tracks. A track with no beat scores (nan, a clip too short to trim) is left out
    of the beat columns' overall; they are nan only when no track has a value.
    """
    import mir_eval

    def row(items: list[dict]) -> dict:
        total = sum(t["duration"] for t in items)

        def weighted(key: str) -> float:
            scored = [t for t in items if not np.isnan(t[key])]
            if not scored:
                return float("nan")
            return sum(t[key] * t["duration"] for t in scored) / sum(t["duration"] for t in scored)

        out = {
            metric: mir_eval.chord.weighted_accuracy(
                np.concatenate([t[metric][0] for t in items]),
                np.concatenate([t[metric][1] for t in items]),
            )
            for metric in METRICS
        }
        for key in ("n_est", "n_ref", "beat_f", "cmlt", "amlt", "nonchord"):
            out[key] = weighted(key)
        # A ratio of sums, so a track weighs by what it adds to that metric, not by its length.
        for key in ("bass_ref", "inv_prec", "inv_rec"):
            hit = sum(t[key][0] for t in items)
            seen = sum(t[key][1] for t in items)
            out[key] = hit / seen if seen else float("nan")
        hit = weighted("n_hit")
        out["n_precision"] = hit / out["n_est"] if out["n_est"] else float("nan")
        out["n_recall"] = hit / out["n_ref"] if out["n_ref"] else float("nan")
        # np.nanmedian, without its RuntimeWarning when every ratio is nan.
        ratios = [t["period_ratio"] for t in items if not np.isnan(t["period_ratio"])]
        out["period_ratio"] = float(np.median(ratios)) if ratios else float("nan")
        out["duration"] = total
        return out

    rows = {name: row([track]) for name, track in tracks.items()}
    rows["overall"] = row(list(tracks.values()))
    return rows


class DatasetError(Exception):
    """A dataset could not be downloaded, unpacked or read (raised where external data enters)."""


def cache_dir() -> Path:
    """Where the datasets are downloaded to."""
    if CACHE_DIR is not None:
        return CACHE_DIR
    # In a checkout the datasets sit in its gitignored datasets/, where they are easy to find and
    # delete; an installed package has no checkout, so it falls back to the user cache.
    if (_CHECKOUT / "pyproject.toml").is_file():
        return _CHECKOUT / "datasets"
    import pooch

    return Path(pooch.os_cache("chordotomy"))


def fetch(archive: str, members: list[str] | None) -> list[Path]:
    """Download `archive` into the cache if needed and extract `members` (all when None)."""
    import pooch

    cache = pooch.create(
        path=cache_dir(),
        base_url="https://zenodo.org/api/records/",
        registry=REGISTRY,
        urls=URLS,
    )
    try:
        paths = cache.fetch(archive, processor=pooch.Unzip(members=members))
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise DatasetError(f"{archive}: {exc}") from exc
    return [Path(p) for p in paths]


def _locate(archive: str, paths: list[Path], names: list[str]) -> dict[str, Path]:
    # pooch skips a member the archive does not contain without a word.
    found = {p.name: p for p in paths}
    for name in names:
        if name not in found:
            raise DatasetError(f"{archive}: {name} is not in the archive")
    return found


def tiny_aam_tracks(limit: int | None) -> list[tuple[str, Path, Path]]:
    """(id, audio, annotation) of the first `limit` Tiny AAM mixes."""
    ids = TINY_AAM_IDS[:limit]
    arff = [f"{i}_beatinfo.arff" for i in ids]
    mp3 = [f"{i}_mix.mp3" for i in ids]
    # Exact members, not directories: pooch extracts again whenever a requested file is missing,
    # so an interrupted extraction heals, and the stems and MIDI files stay in the archive.
    members = [f"annotations/{a}" for a in arff] + [f"audio-mixes-mp3/{m}" for m in mp3]
    found = _locate("tinyAAM.zip", fetch("tinyAAM.zip", members), arff + mp3)
    return [(i, found[m], found[a]) for i, a, m in zip(ids, arff, mp3, strict=True)]


def guitarset_tracks(limit: int | None) -> list[tuple[str, Path, Path]]:
    """(stem, audio, annotation) of the first `limit` GuitarSet accompaniment takes."""
    annotations = fetch("annotation.zip", None)
    jams = sorted(p for p in annotations if p.name.endswith("_comp.jams"))[:limit]
    stems = [p.name.removesuffix(".jams") for p in jams]
    wavs = [f"{stem}_mic.wav" for stem in stems]
    # The audio zip is 657 MB: extract only these takes. A later run asking for more extracts
    # the rest, because pooch extracts again whenever a requested member is missing.
    found = _locate("audio_mono-mic.zip", fetch("audio_mono-mic.zip", wavs), wavs)
    return [(stem, found[wav], j) for stem, wav, j in zip(stems, wavs, jams, strict=True)]


def _read_reference(dataset: str, path: Path, duration: float) -> Reference:
    try:
        if dataset == "tiny-aam":
            return tiny_aam_reference(path.read_text(), duration)
        return guitarset_reference(json.loads(path.read_text()))
    except (OSError, ValueError) as exc:
        raise DatasetError(f"{path}: {exc}") from exc


def run(dataset: str, limit: int | None, engine: Literal["dsp", "model"]) -> dict[str, dict]:
    """Analyze and score every track of `dataset`, print the table, and return the summary."""
    tracks = tiny_aam_tracks(limit) if dataset == "tiny-aam" else guitarset_tracks(limit)
    scored = {}
    for name, audio, annotation in tracks:
        result = timeline.analyze(audio, engine=engine)
        reference = _read_reference(dataset, annotation, result["source"]["duration"])
        est_intervals, est_labels = timeline_to_intervals(result)
        scored[name] = {
            **score(
                reference.intervals,
                reference.labels,
                est_intervals,
                est_labels,
                bass_missing(result),
            ),
            # The grid analyze writes, extended to the edges: the one every consumer snaps to.
            **beat_metrics(reference.beats, np.array(result["beats"], dtype=float)),
            **bass_metrics(result, reference),
        }
    rows = summarise(scored)

    columns = (*METRICS, "n_est", "n_ref", "n_precision", "n_recall")
    columns += ("beat_f", "cmlt", "amlt", "period_ratio")
    columns += ("bass_ref", "inv_prec", "inv_rec", "nonchord")
    header = (*METRICS, "N_est", "N_ref", "N_prec", "N_rec", "beat_F", "CMLt", "AMLt", "period")
    header += ("bass_ref", "inv_prec", "inv_rec", "nonchord")
    # Width 8, widened for a heading that would otherwise run into its neighbour.
    widths = [max(8, len(h) + 1) for h in header]
    print(f"{'track':<28}" + "".join(f"{h:>{w}}" for h, w in zip(header, widths, strict=True)))
    for name in (*scored, "overall"):
        cells = (f"{rows[name][c]:>{w}.3f}" for c, w in zip(columns, widths, strict=True))
        print(f"{name:<28}" + "".join(cells))
    return rows

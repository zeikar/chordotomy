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

import numpy as np

from . import timeline
from .chords import ROOTS

METRICS = ("root", "majmin", "sevenths", "majmin_inv")

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


def tiny_aam_reference(text: str, duration: float) -> tuple[np.ndarray, list[str]]:
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
    intervals = np.column_stack([starts, [*starts[1:], duration]]).astype(float)
    return intervals, labels


def guitarset_reference(jams: dict) -> tuple[np.ndarray, list[str]]:
    """The performed chord annotation of a GuitarSet JAMS dict (it carries the bass)."""
    performed = [
        a
        for a in jams["annotations"]
        if a["namespace"] == "chord"
        and a["annotation_metadata"]["data_source"].startswith("Semi-automatic")
    ]
    if len(performed) != 1:
        raise ValueError(f"expected one Semi-automatic chord annotation, found {len(performed)}")
    data = performed[0]["data"]
    intervals = np.array([(d["time"], d["time"] + d["duration"]) for d in data], dtype=float)
    return intervals, [d["value"] for d in data]


def score(
    ref_intervals: np.ndarray,
    ref_labels: list[str],
    est_intervals: np.ndarray,
    est_labels: list[str],
    est_bass_missing: list[bool] | None = None,
) -> dict:
    """One track's per-interval comparisons and durations for each metric, plus the N shares.

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
    track["n_est"] = float(durations[np.array(est) == "N"].sum()) / total
    track["n_ref"] = float(durations[np.array(ref) == "N"].sum()) / total
    track["duration"] = total
    return track


def summarise(tracks: dict[str, dict]) -> dict[str, dict]:
    """Accuracy and N rates per track, plus an `overall` row weighted by duration."""
    import mir_eval

    def row(items: list[dict]) -> dict:
        total = sum(t["duration"] for t in items)
        out = {
            metric: mir_eval.chord.weighted_accuracy(
                np.concatenate([t[metric][0] for t in items]),
                np.concatenate([t[metric][1] for t in items]),
            )
            for metric in METRICS
        }
        for rate in ("n_est", "n_ref"):
            out[rate] = sum(t[rate] * t["duration"] for t in items) / total
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


def _read_reference(dataset: str, path: Path, duration: float) -> tuple[np.ndarray, list[str]]:
    try:
        if dataset == "tiny-aam":
            return tiny_aam_reference(path.read_text(), duration)
        return guitarset_reference(json.loads(path.read_text()))
    except (OSError, ValueError) as exc:
        raise DatasetError(f"{path}: {exc}") from exc


def run(dataset: str, limit: int | None) -> dict[str, dict]:
    """Analyze and score every track of `dataset`, print the table, and return the summary."""
    tracks = tiny_aam_tracks(limit) if dataset == "tiny-aam" else guitarset_tracks(limit)
    scored = {}
    for name, audio, annotation in tracks:
        result = timeline.analyze(audio)
        ref_intervals, ref_labels = _read_reference(
            dataset, annotation, result["source"]["duration"]
        )
        est_intervals, est_labels = timeline_to_intervals(result)
        scored[name] = score(
            ref_intervals, ref_labels, est_intervals, est_labels, bass_missing(result)
        )
    rows = summarise(scored)

    columns = (*METRICS, "n_est", "n_ref")
    header = (*METRICS, "N_est", "N_ref")
    print(f"{'track':<28}" + "".join(f"{c:>11}" for c in header))
    for name in (*scored, "overall"):
        print(f"{name:<28}" + "".join(f"{rows[name][c]:>11.3f}" for c in columns))
    return rows

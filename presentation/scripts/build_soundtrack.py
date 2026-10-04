"""Compose the original FastFence instrumental; no samples or speech are used.

Requires an existing NumPy environment and local FFmpeg. The stereo master stays
private; the distributable output is AAC at 192 kbit/s. Randomness is seeded.
Arrangement: 120 BPM, D minor, 55 bars, 110 seconds. Warm pads, rounded plucks,
sub bass and synthesized percussion develop across three distinct sections.
"""

import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from soundtrack_synthesis import DURATION, RATE, compose


def write_wave(path, signal):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(
            (np.clip(signal, -1, 1) * 32767).astype("<i2").tobytes()
        )


def loudness(path):
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "loudnorm=I=-18:TP=-1.5:LRA=9:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.JSONDecoder().raw_decode(
        result.stderr[result.stderr.rfind("{") :]
    )[0]


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "presentation/output/fastfence-soundtrack.m4a",
    )
    parser.add_argument("--duration", type=int, default=DURATION)
    parser.add_argument("--soft-start", type=int, default=60)
    parser.add_argument("--soft-end", type=int, default=90)
    args = parser.parse_args()
    if args.duration < 30 or args.duration % 2:
        parser.error("duration must be an even number of seconds, at least 30")
    if not 0 <= args.soft_start < args.soft_end <= args.duration:
        parser.error("soft section must fall inside the track duration")
    private = root / "state/private/soundtrack"
    private.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    master = private / "original-master.wav"
    write_wave(master, compose(args.duration, args.soft_start, args.soft_end))
    levels = loudness(master)
    normalizer = "loudnorm=I=-18:TP=-1.5:LRA=9:linear=true:" + ":".join(
        f"{key}={levels[value]}"
        for key, value in [
            ("measured_I", "input_i"),
            ("measured_TP", "input_tp"),
            ("measured_LRA", "input_lra"),
            ("measured_thresh", "input_thresh"),
            ("offset", "target_offset"),
        ]
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(master),
            "-af",
            normalizer,
            "-ar",
            str(RATE),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-metadata",
            "title=FastFence - Signal and Control",
            "-metadata",
            "comment=Original instrumental generated for FastFence; synthesized, no sampled music or speech.",
            "-movflags",
            "+faststart",
            str(args.output),
        ],
        check=True,
    )
    measured = loudness(args.output)
    if (
        float(measured["input_tp"]) > -1
        or abs(float(measured["input_i"]) + 18) > 0.5
    ):
        raise SystemExit(
            "Final encoded loudness is outside the delivery bounds"
        )
    report = {
        "title": "Signal and Control",
        "duration_seconds": args.duration,
        "attribution": "Original instrumental generated for FastFence",
        "method": "Seeded additive and noise synthesis; no recordings, samples, or speech",
        "bpm": 120,
        "key": "D minor",
        "sample_rate": RATE,
        "channels": 2,
        "integrated_lufs": float(measured["input_i"]),
        "true_peak_dbtp": float(measured["input_tp"]),
        "loudness_range_lu": float(measured["input_lra"]),
    }
    (private / "levels.json").write_text(json.dumps(report, indent=2) + "\n")
    sys.stdout.write(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()

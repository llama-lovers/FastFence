"""Original deterministic musical arrangement and synthesis for FastFence."""

import numpy as np

RATE = 48_000
DURATION = 110
BEAT = 0.5
RNG = np.random.default_rng(20261004)


def frequency(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def envelope(t, attack, release, duration):
    return np.minimum(t / attack, 1) * np.minimum(
        np.maximum(duration - t, 0) / release, 1
    )


def tone(midi, duration, kind="pad"):
    t = np.arange(round(duration * RATE), dtype=np.float32) / RATE
    f = frequency(midi)
    if kind == "pad":
        out = sum(
            np.sin(2 * np.pi * f * ratio * t + phase) * gain
            for ratio, phase, gain in [
                (1, 0, 0.6),
                (0.9987, 1, 0.18),
                (1.0014, 2, 0.18),
                (2, 0.3, 0.13),
                (3, 0.7, 0.04),
            ]
        )
        return out * envelope(t, 0.45, 0.85, duration) * 0.4
    if kind == "bass":
        out = np.sin(2 * np.pi * f * t)
        out += 0.18 * np.sin(4 * np.pi * f * t)
        out += 0.07 * np.sin(6 * np.pi * f * t)
        return out * envelope(t, 0.015, 0.10, duration) * np.exp(-t * 0.6)
    out = np.sin(2 * np.pi * f * t) * np.exp(-t * 4.4)
    out += 0.19 * np.sin(4 * np.pi * f * t) * np.exp(-t * 10)
    out += 0.045 * np.sin(6 * np.pi * f * t) * np.exp(-t * 17)
    return out * envelope(t, 0.009, 0.10, duration)


def filtered_noise(duration, low, high):
    n = round(duration * RATE)
    noise = RNG.normal(0, 1, n)
    bins = np.fft.rfftfreq(n, 1 / RATE)
    weights = np.minimum(bins / max(low, 1), 1) ** 4
    weights *= np.exp(-((bins / high) ** 4))
    signal = np.fft.irfft(np.fft.rfft(noise) * weights, n=n)
    return signal.astype(np.float32) / max(float(np.std(signal)), 1e-6)


def percussion(kind):
    duration = {
        "kick": 0.43,
        "snare": 0.25,
        "hat": 0.075,
        "open_hat": 0.19,
        "rise": 1.5,
    }[kind]
    t = np.arange(round(duration * RATE), dtype=np.float32) / RATE
    if kind == "kick":
        phase = 2 * np.pi * (49 * t + 45 * 0.028 * (1 - np.exp(-t / 0.028)))
        signal = np.sin(phase) * np.exp(-t * 11)
        signal += (
            0.035 * filtered_noise(duration, 1200, 3600) * np.exp(-t * 150)
        )
        return signal * envelope(t, 0.002, 0.045, duration)
    if kind == "snare":
        signal = filtered_noise(duration, 650, 6500) * np.exp(-t * 23) * 0.34
        signal += np.sin(2 * np.pi * 185 * t) * np.exp(-t * 28) * 0.22
        return signal * envelope(t, 0.002, 0.04, duration)
    if kind == "rise":
        return filtered_noise(duration, 1100, 4300) * (t / duration) ** 2 * 0.12
    decay = 58 if kind == "hat" else 21
    return filtered_noise(duration, 5200, 12000) * np.exp(-t * decay) * 0.17


def add(track, signal, start, gain=1, pan=0):
    offset = round(start * RATE)
    count = min(len(signal), len(track) - offset)
    if offset < 0 or count <= 0:
        return
    theta = (pan + 1) * np.pi / 4
    track[offset : offset + count, 0] += signal[:count] * gain * np.cos(theta)
    track[offset : offset + count, 1] += signal[:count] * gain * np.sin(theta)


def space(signal):
    wet = np.zeros_like(signal)
    for seconds, gain in [
        (0.073, 0.15),
        (0.127, 0.11),
        (0.193, 0.09),
        (0.281, 0.07),
        (0.397, 0.05),
        (0.563, 0.035),
    ]:
        shift = round(seconds * RATE)
        wet[shift:] += signal[:-shift, ::-1] * gain
    return signal + wet


def render_notes(bar, start, root, chord, soft, outro, strength, bass, melody):
    if bar >= 2 and bar < 52:
        offsets = [0, 1.5, 2.5, 3.5] if not soft else [0, 2.5]
        for beat in offsets:
            note = root + (12 if beat == 3.5 and bar % 4 == 3 else 0)
            add(
                bass,
                tone(note, 0.42, "bass"),
                start + beat * BEAT,
                0.16 * strength,
            )
    # Two related motifs vary register, harmony and rhythm every phrase.
    if bar >= 4:
        rhythm = [0.5, 1.25, 2, 3.25] if soft else [0.5, 1.25, 2, 2.75, 3.5]
        if outro:
            rhythm = [0.5, 2]
        for index, beat in enumerate(rhythm):
            sequence = (
                [0, 2, 1, 3, 2] if (bar // 8) % 2 == 0 else [2, 1, 3, 0, 1]
            )
            note = chord[sequence[index] % len(chord)]
            add(
                melody,
                tone(note, 1.1, "pluck"),
                start + beat * BEAT,
                0.095 * strength,
                (-0.38 if index % 2 else 0.38),
            )


def render_drums(
    bar, start, soft, outro, strength, hits, drums, kick_times, end_bar
):
    if bar < 6 or bar >= end_bar:
        return
    beats = [0, 2] if soft or bar < 10 or outro else [0, 1, 2, 3]
    for beat in beats:
        moment = start + beat * BEAT
        add(drums, hits["kick"], moment, 0.40 * strength)
        kick_times.append(moment)
    if bar >= 8 and not (soft and bar % 2):
        for beat in [1, 3]:
            add(
                drums, hits["snare"], start + beat * BEAT, 0.25 * strength, 0.04
            )
    for index, beat in enumerate(np.arange(0.5, 4, 0.5)):
        if soft and index % 2:
            continue
        gain = (0.18 if index % 2 else 0.25) * strength
        add(
            drums,
            hits["hat"],
            start + beat * BEAT,
            gain,
            0.27 if index % 2 else -0.27,
        )
    if not soft and bar >= 12 and bar % 2:
        add(drums, hits["open_hat"], start + 3.5 * BEAT, 0.13, 0.35)
    if bar in [7, 15, 23, 44, 47]:
        add(drums, hits["rise"], start + 0.5, 0.11, -0.1)


def compose(duration=DURATION, soft_start=60, soft_end=90):
    shape = (duration * RATE, 2)
    pads = np.zeros(shape, np.float32)
    melody = np.zeros(shape, np.float32)
    bass = np.zeros(shape, np.float32)
    drums = np.zeros(shape, np.float32)
    # Dm9, Bbmaj7, Fmaj9, Csus2: a coherent eight-bar harmonic cycle.
    harmony = [
        (38, [62, 65, 69, 72, 76]),
        (34, [58, 62, 65, 69]),
        (41, [60, 64, 65, 69, 72]),
        (36, [60, 62, 67, 74]),
    ]
    hits = {
        name: percussion(name)
        for name in ["kick", "snare", "hat", "open_hat", "rise"]
    }
    kick_times = []
    for bar in range(duration // 2 - 1):
        start = bar * 2
        root, chord = harmony[(bar // 2) % 4]
        soft = soft_start <= start < soft_end
        outro = start >= duration - 10
        strength = 0.66 if soft else 1
        if bar % 2 == 0:
            for index, note in enumerate(chord):
                add(
                    pads,
                    tone(note, 4.6),
                    start,
                    0.10 * strength,
                    (index / (len(chord) - 1) * 1.5) - 0.75,
                )
        render_notes(
            bar, start, root, chord, soft, outro, strength, bass, melody
        )
        render_drums(
            bar,
            start,
            soft,
            outro,
            strength,
            hits,
            drums,
            kick_times,
            duration // 2 - 2,
        )
    # Resolve to Dm9 instead of stopping on a repeating loop.
    for index, note in enumerate([50, 62, 65, 69, 76]):
        add(pads, tone(note, 3.9), duration - 4, 0.14, -0.6 + index * 0.3)
    add(melody, tone(74, 2, "pluck"), duration - 3, 0.08, 0.25)
    add(bass, tone(38, 2, "bass"), duration - 4, 0.18)
    for seconds, gain in [(0.375, 0.23), (0.75, 0.10), (1.125, 0.045)]:
        shift = round(seconds * RATE)
        melody[shift:] += melody[:-shift, ::-1].copy() * gain
    duck = np.ones(len(pads), np.float32)
    curve = 1 - 0.22 * np.exp(-np.arange(round(0.32 * RATE)) / RATE / 0.095)
    for moment in kick_times:
        offset = round(moment * RATE)
        duck[offset : offset + len(curve)] = np.minimum(
            duck[offset : offset + len(curve)], curve
        )
    mix = space(pads) * duck[:, None] + space(melody) + bass + drums
    fade = np.minimum(np.arange(len(mix)) / (2 * RATE), 1)
    fade *= np.minimum(np.arange(len(mix))[::-1] / (3 * RATE), 1)
    mix *= fade[:, None]
    mix *= 0.82 / max(float(np.abs(mix).max()), 1e-9)
    return mix

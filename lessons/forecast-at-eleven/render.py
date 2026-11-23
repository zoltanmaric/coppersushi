"""Encode six animated scenes using the timing of the spoken narration."""

import argparse
import json
import math
import subprocess
from bisect import bisect_right
from pathlib import Path

from art import frame

BUILD = Path(__file__).resolve().parent / "build"
FPS = 18
# Each spoken phrase lands on the matching visual reveal.
BEATS = (
    (),
    (("The second says", 0.42),),
    (("published by eleven", 0.48),),
    (("Your collector receives", 0.50),),
    (("At eleven, the score", 0.30), ("At noon", 0.45), ("seven point one six", 0.71)),
    (("At eleven you get eighty", 0.23), ("At eleven twenty you get", 0.61)),
)


def cue_points(scene, duration):
    timing = json.loads((BUILD / "audio" / f"{scene:02}.json").read_text())
    speech = "".join(timing["characters"]).casefold()
    points = [(0.0, 0.0)]
    for phrase, fraction in BEATS[scene]:
        start = speech.index(phrase.casefold())
        points.append((timing["character_start_times_seconds"][start], fraction))
    return points + [(duration, 1.0)]


def render_scene(scene):
    audio = BUILD / "audio" / f"{scene:02}.mp3"
    duration = float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(audio),
            ]
        )
    )
    points = cue_points(scene, duration)
    times = [t for t, _ in points]
    count = math.ceil((duration + 0.55) * FPS)
    clip = BUILD / f"scene-{scene:02}.mp4"
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        "1280x720",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-i",
        str(audio),
        "-af",
        "apad",
        "-t",
        str(count / FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(clip),
    ]
    with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
        for index in range(count):
            t = min(index / FPS, duration)
            segment = min(bisect_right(times, t) - 1, len(points) - 2)
            start, low = points[segment]
            end, high = points[segment + 1]
            progress = low + (t - start) / (end - start) * (high - low)
            encoder.stdin.write(frame(scene, progress).tobytes())
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError(f"Could not encode scene {scene}")
    print(f"Rendered {clip.name} ({count / FPS:.1f}s)", flush=True)
    return clip


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scene", type=int, choices=range(6), help="Render one scene (0–5)"
    )
    args = parser.parse_args()
    chosen = range(6) if args.scene is None else [args.scene]
    clips = [render_scene(i) for i in chosen]
    if args.scene is None:
        sequence = BUILD / "scenes.ffconcat"
        sequence.write_text("".join(f"file '{clip.name}'\n" for clip in clips))
        pending = BUILD / "episode.pending.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "concat",
                "-i",
                str(sequence),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(pending),
            ],
            check=True,
        )
        pending.replace(BUILD / "the-1100-forecast.mp4")


if __name__ == "__main__":
    main()

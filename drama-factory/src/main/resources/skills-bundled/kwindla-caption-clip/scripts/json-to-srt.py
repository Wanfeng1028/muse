#!/usr/bin/env python3
"""Convert a Deepgram utterances transcript into an SRT subtitle file.

Usage:
    python3 json-to-srt.py input.json output.srt

The input must be a Deepgram response produced with the `utterances=true`
option, so that `results.utterances` exists. Each utterance becomes one
SRT cue.
"""

import argparse
import json
import sys


def seconds_to_timestamp(value):
    """Render a float number of seconds as SRT time `HH:MM:SS,mmm`."""
    if value < 0:
        value = 0.0
    total_ms = int(round(value * 1000))
    hours, remainder = divmod(total_ms, 3600 * 1000)
    minutes, remainder = divmod(remainder, 60 * 1000)
    secs, millis = divmod(remainder, 1000)
    return "{:02d}:{:02d}:{:02d},{:03d}".format(hours, minutes, secs, millis)


def load_utterances(path):
    """Read the JSON file and return the list of utterances."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    results = payload.get("results")
    if not isinstance(results, dict):
        raise ValueError("input JSON has no 'results' object")

    utterances = results.get("utterances")
    if not utterances:
        raise ValueError(
            "input JSON has no 'results.utterances'; "
            "re-run Deepgram with utterances=true"
        )
    return utterances


def write_srt(utterances, path):
    """Write each utterance as a numbered SRT cue."""
    count = 0
    with open(path, "w", encoding="utf-8") as handle:
        for index, item in enumerate(utterances, start=1):
            start = item.get("start")
            end = item.get("end")
            text = (item.get("transcript") or "").strip()

            if start is None or end is None or not text:
                continue

            handle.write("{}\n".format(index))
            handle.write("{} --> {}\n".format(
                seconds_to_timestamp(float(start)),
                seconds_to_timestamp(float(end)),
            ))
            handle.write("{}\n\n".format(text))
            count += 1
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert Deepgram utterances JSON to SRT subtitles."
    )
    parser.add_argument("input", help="path to the Deepgram JSON transcript")
    parser.add_argument("output", help="path to write the SRT file")
    args = parser.parse_args(argv)

    try:
        utterances = load_utterances(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as err:
        print("Error: {}".format(err), file=sys.stderr)
        return 1

    written = write_srt(utterances, args.output)
    print("Wrote {} cues to {}".format(written, args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())

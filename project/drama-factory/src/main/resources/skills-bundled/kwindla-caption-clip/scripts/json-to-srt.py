#!/usr/bin/env python3
"""
Convert Deepgram JSON transcript to SRT subtitle format.

Usage:
    python3 json-to-srt.py input.json output.srt
"""

import json
import sys


def format_time(seconds: float) -> str:
    """Convert seconds to SRT time format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def json_to_srt(json_path: str, srt_path: str) -> None:
    """Convert Deepgram JSON transcript to SRT format."""
    with open(json_path, 'r') as f:
        data = json.load(f)

    # Extract utterances from Deepgram response
    if 'results' not in data or 'utterances' not in data['results']:
        print("Error: No utterances found in JSON. Ensure Deepgram was called with utterances=true")
        sys.exit(1)

    utterances = data['results']['utterances']

    with open(srt_path, 'w') as f:
        for i, utterance in enumerate(utterances, 1):
            start = format_time(utterance['start'])
            end = format_time(utterance['end'])
            text = utterance['transcript']
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

    print(f"Created {srt_path} with {len(utterances)} subtitles")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python3 json-to-srt.py input.json output.srt")
        sys.exit(1)

    json_to_srt(sys.argv[1], sys.argv[2])

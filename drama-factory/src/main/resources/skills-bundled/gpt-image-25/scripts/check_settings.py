"""Offline consistency checks for the supplied GPT Image 2.5 guide (2026-09-09)."""

import argparse
import json
import re


def check_settings(size="auto", background="auto", output_format="png"):
    errors, warnings = [], []
    if size != "auto":
        match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", size)
        if not match:
            errors.append("size must be auto or WIDTHxHEIGHT with positive integers.")
        else:
            width, height = map(int, match.groups())
            pixels = width * height
            if max(width, height) > 3840:
                errors.append("Each edge must be at most 3840 pixels.")
            if width % 16 or height % 16:
                errors.append("Both edges must be multiples of 16.")
            if max(width, height) > 3 * min(width, height):
                errors.append("The longer-to-shorter edge ratio must not exceed 3:1.")
            if not 655360 <= pixels <= 8294400:
                errors.append("Total pixels must be between 655360 and 8294400.")
            if not errors and pixels > 3686400:
                warnings.append("Experimental output: more than 3686400 pixels.")
    if background == "transparent" and output_format == "jpeg":
        errors.append("Transparent output requires PNG or WebP, not JPEG.")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", default="auto")
    parser.add_argument("--model", choices=["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"])
    parser.add_argument("--quality", choices=["auto", "low", "medium", "high", "xhigh", "max"], default="auto")
    parser.add_argument("--background", choices=["auto", "opaque", "transparent"], default="auto")
    parser.add_argument("--output-format", choices=["png", "jpeg", "webp"], default="png")
    parser.add_argument("--output-compression", type=int)
    args = parser.parse_args()
    result = check_settings(args.size, args.background, args.output_format)
    if args.output_compression is not None:
        if args.output_format == "png":
            result["errors"].append("Omit output_compression for PNG.")
        else:
            result["warnings"].append("Compression range is not validated; check the current API schema.")
    result["valid"] = not result["errors"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

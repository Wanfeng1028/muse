"""CLI flags and subcommands (pick, contact-sheet, check-alpha, batch-fetch) for gen_image.py."""
import argparse
import sys
from pathlib import Path

from _gen_image_spec import ASPECT_PRESETS

sys.dont_write_bytecode = True


def add_generation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", type=Path, default=Path("public/img"), help="output folder (default public/img)")
    parser.add_argument("--provider", choices=["openai", "gemini", "bfl", "recraft"], help="override every image's provider (default openai)")
    parser.add_argument("--model", help="override the model id (default gpt-image-2.5-flare for openai)")
    parser.add_argument("--quality", help="override quality: low|medium|high|auto, xhigh|max on gpt-image-2.5")
    parser.add_argument("--final", action="store_true", help="finals: gpt-image-2.5-sunburst, quality high")
    parser.add_argument("--draft", action="store_true", help="drafts: quality low, n=4, ~1 MP, written to <out>/drafts/")
    parser.add_argument("--aspect", choices=sorted(ASPECT_PRESETS), help="size preset: 16:9=2048x1152 9:16=1152x2048 1:1=1536x1536 4:5=1280x1600")
    parser.add_argument("--overscan", type=float, help="scale the size up by this factor for camera moves (capped by the limits)")
    parser.add_argument("--composite-back", action="store_true", help="masked edits: paste only the masked region over Image 1 (pixel-exact)")
    parser.add_argument("--feather", type=float, default=2.0, help="composite-back mask feather in px (default 2)")
    parser.add_argument("--moderation", choices=["auto", "low"], help="OpenAI moderation level (default: API default auto)")
    parser.add_argument("--regenerate", action="store_true", help="redo existing images (old files archived as raw/<name>.vN.<ext>)")
    parser.add_argument("--concurrency", type=int, default=2, help="requests in flight (default 2, capped at --ipm)")
    parser.add_argument("--ipm", type=int, default=20, help="images per minute for your tier (default 20 = OpenAI Build)")
    parser.add_argument("--budget", type=float, help="stop starting requests once spend (from usage) would pass this USD")
    parser.add_argument("--batch", action="store_true", help="submit through the OpenAI Batch API (half price, up to 24 h)")
    parser.add_argument("--contact-sheet", type=Path, help="write a labelled grid of this run's images to this PNG")
    parser.add_argument("--env-file", type=Path, help="KEY=VALUE file with the provider API keys")
    parser.add_argument("--dry-run", action="store_true", help="print the exact requests, sizes, refs and cost estimate; send nothing")


def pick_command(argv: list[str]) -> int:
    from _gen_image_review import pick
    parser = argparse.ArgumentParser(prog="gen_image.py pick", description="Promote one variant (NAME.LETTER.*) to NAME.* and archive the rest to raw/.",
                                     epilog="example: gen_image.py pick cast b --dir public/img/drafts")
    parser.add_argument("name")
    parser.add_argument("letter", help="variant letter a-j")
    parser.add_argument("--dir", type=Path, default=Path("public/img"), help="folder holding the variants (default public/img)")
    args = parser.parse_args(argv)
    return pick(args.dir, args.name, args.letter.lower())


def contact_sheet_command(argv: list[str]) -> int:
    from _gen_image_review import contact_sheet
    parser = argparse.ArgumentParser(prog="gen_image.py contact-sheet", description="Labelled grid of images (alpha shown over a checkerboard).",
                                     epilog="example: gen_image.py contact-sheet public/img/cast.png public/img/shot-*.png --out out/review/cast.png")
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="sheet PNG to write")
    parser.add_argument("--columns", type=int, default=4, help="grid columns (default 4)")
    parser.add_argument("--cell", type=int, default=320, help="cell size in px (default 320)")
    args = parser.parse_args(argv)
    contact_sheet(args.images, args.out, args.columns, args.cell)
    return 0


def check_alpha_command(argv: list[str]) -> int:
    from _gen_image_output import alpha_failure, alpha_report
    parser = argparse.ArgumentParser(prog="gen_image.py check-alpha", description="Verify real transparency (a painted checkerboard is not alpha).",
                                     epilog="PASS needs an alpha channel with >1% fully transparent pixels. example: gen_image.py check-alpha public/img/*.png")
    parser.add_argument("images", nargs="+", type=Path)
    args = parser.parse_args(argv)
    failures = 0
    for path in args.images:
        report = alpha_report(path)
        failure = alpha_failure(report)
        failures += failure is not None
        state = f"FAIL ({failure})" if failure else "PASS"
        print(f"{state} {path}: {report['size']}, alpha={report['has_alpha']}, fully transparent {report['transparent_share']:.2%}")
    print(f"{len(args.images) - failures}/{len(args.images)} PASS")
    return 1 if failures else 0


def batch_fetch_command(argv: list[str]) -> int:
    from _gen_image_batch import fetch
    from _gen_image_http import load_env_file, require_key
    parser = argparse.ArgumentParser(prog="gen_image.py batch-fetch", description="Check a --batch job; when completed, write its images and sidecars.",
                                     epilog="example: gen_image.py batch-fetch batch_abc123 --out public/img --env-file .env.local")
    parser.add_argument("batch_id")
    parser.add_argument("--out", type=Path, default=Path("public/img"), help="the --out used when submitting")
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args(argv)
    load_env_file(args.env_file)
    return fetch(args.batch_id, args.out, require_key("openai"))


SUBCOMMANDS = {"pick": pick_command, "contact-sheet": contact_sheet_command, "check-alpha": check_alpha_command,
               "batch-fetch": batch_fetch_command}

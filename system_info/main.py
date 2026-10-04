#!/usr/bin/env python3
"""CLI entry point. Thin layer only: all logic lives in the package.

Usage:
    ./main.py                 # all categories, colored console output
    ./main.py cpu memory      # only selected categories
    ./main.py --json          # machine-readable snapshot
    ./main.py --no-color      # plain text
    ./main.py --list          # list categories
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Allow running this file directly from anywhere.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from system_info.app import SystemInfoApp  # noqa: E402
from system_info.renderers.text import ConsoleRenderer  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    app = SystemInfoApp()
    parser = argparse.ArgumentParser(
        prog="system_info",
        description="In-depth system information (GUI-ready architecture).",
        epilog=f"categories: {', '.join(app.category_names)}",
    )
    parser.add_argument("categories", nargs="*", help="categories to show (default: all)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    parser.add_argument("--list", action="store_true", help="list available categories and exit")
    parser.add_argument("--parallel", action="store_true", default=True,
                        help="collect categories concurrently (default)")
    parser.add_argument("--sequential", action="store_false", dest="parallel",
                        help="collect categories one at a time")
    args = parser.parse_args(argv)

    if args.list:
        print(f"{'overview':10s}  Overall system summary")
        for klass in app.collectors:
            print(f"{klass.name:10s}  {klass.title}")
        return 0

    if args.categories:
        unknown=set(args.categories)-set(app.category_names)
        if unknown:parser.error("unknown categories: " + ", ".join(sorted(unknown)))
        snapshot = app.collect(args.categories)
    else:
        snapshot = app.collect_all(parallel=args.parallel)

    if args.json:
        print(json.dumps(snapshot.to_dict(), indent=2, default=str))
    else:
        renderer = ConsoleRenderer(color=not args.no_color)
        print(renderer.render(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
import os
import sys
import threading

# Allow running this file directly from anywhere.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from system_info.app import SystemInfoApp  # noqa: E402
from system_info.reports import render_report, write_report  # noqa: E402
from system_info.cancellation import Cancelled  # noqa: E402
from system_info.version import VERSION  # noqa: E402


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
    parser.add_argument('--version', action='version', version=f'System Info {VERSION}')
    parser.add_argument('--include-identifiers', action='store_true', help='include identifiers (default: hide known identifiers)')
    parser.add_argument('--output', metavar='PATH', help='write report atomically to a file; JSON with --json, text otherwise; - means stdout')
    parser.add_argument('--progress', action='store_true', help='show collection progress on stderr')
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

    unknown=set(args.categories)-set(app.category_names)
    if unknown:parser.error("unknown categories: " + ", ".join(sorted(unknown)))
    cancel = threading.Event()
    progress = (lambda done, total, title: print(f'{done}/{total} {title}', file=sys.stderr)) if args.progress else None
    try:
        snapshot = (app.collect(args.categories, parallel=args.parallel, cancel=cancel, progress=progress) if args.categories else
                    app.collect_all(parallel=args.parallel, cancel=cancel, progress=progress))
        report = render_report(snapshot, 'json' if args.json else 'text', not args.include_identifiers,
                               color=not args.no_color and not args.output)
        if args.output and args.output != '-':
            write_report(args.output, report)
        else:
            print(report, end='')
        return 0
    except (KeyboardInterrupt, Cancelled):
        cancel.set()
        print('Interrupted; incomplete report files are discarded.', file=sys.stderr)
        return 130
    except (OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

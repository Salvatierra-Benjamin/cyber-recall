from __future__ import annotations

import argparse
import sys

from cyber_recall.config import Config
from cyber_recall.db.repository import Repository
from cyber_recall.parsers.sync import SyncReport, sync_notes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cyber-recall",
        description="Active Recall & Spaced Repetition (SM-2) from Markdown notes.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.toml (default: config.toml in the current directory)",
    )
    subparsers = parser.add_subparsers(dest="command", title="commands")

    sync_parser = subparsers.add_parser("sync", help="Sync Markdown notes into the database")
    sync_parser.add_argument(
        "--verbose", action="store_true", help="Show per-module and per-type counts"
    )

    subparsers.add_parser("study", help="Start a study session (Phase 3+)")
    subparsers.add_parser("stats", help="Show progress statistics (Phase 6)")
    subparsers.add_parser("search", help="Search cards quickly (Phase 5)")

    return parser


def _load_config(config_arg: str | None) -> Config:
    path = config_arg or "config.toml"
    try:
        return Config.load(path)
    except FileNotFoundError:
        print(
            f"error: config file not found at '{path}'. "
            f"Run from the project root or pass --config.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _print_sync_report(report: SyncReport, verbose: bool) -> None:
    print(
        f"sync: {report.added} added, {report.updated} updated, "
        f"{report.unchanged} unchanged, {report.archived} archived"
    )
    print(f"total active cards: {report.total_cards}")

    if verbose:
        if report.cards_by_type:
            print("by type:")
            for card_type, count in sorted(report.cards_by_type.items()):
                print(f"  {card_type}: {count}")
        if report.cards_by_module:
            print("by module:")
            for module, count in sorted(report.cards_by_module.items()):
                print(f"  {module}: {count}")

    if report.warnings:
        print(f"warnings ({len(report.warnings)}):")
        for warning in report.warnings:
            print(f"  - {warning}")


def _cmd_sync(config: Config, verbose: bool) -> int:
    with Repository.connect(config.database_path) as repo:
        report = sync_notes(config.notes_dir, repo)
    _print_sync_report(report, verbose)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    config = _load_config(args.config)

    if args.command == "sync":
        return _cmd_sync(config, args.verbose)

    print(f"cyber-recall {args.command}: not implemented yet (planned for a later phase).")
    return 0

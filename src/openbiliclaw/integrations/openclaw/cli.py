"""JSON CLI bridge for the OpenClaw adapter."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .bootstrap import build_openclaw_adapter
from .errors import AdapterOperationError, AdapterValidationError
from .schemas import FeedbackRequest
from .skill import build_openclaw_skills

if TYPE_CHECKING:
    from collections.abc import Sequence

_SKILL_PACK_PATH = (
    Path(__file__).resolve().parents[4] / "skills" / "openbiliclaw-adapter" / "SKILL.md"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openbiliclaw-openclaw")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sync-account")
    subparsers.add_parser("get-profile")
    subparsers.add_parser("runtime-status")
    subparsers.add_parser("doctor")
    subparsers.add_parser("emit-skill-descriptors")

    recommend_parser = subparsers.add_parser("recommend")
    recommend_parser.add_argument("--limit", type=int, default=5)
    refresh_group = recommend_parser.add_mutually_exclusive_group()
    refresh_group.add_argument(
        "--refresh-if-needed",
        action="store_true",
        help="Trigger runtime refresh before returning recommendations.",
    )
    refresh_group.add_argument(
        "--skip-refresh",
        action="store_true",
        help="Skip runtime refresh and only read/generate recommendations.",
    )

    feedback_parser = subparsers.add_parser("submit-feedback")
    feedback_parser.add_argument("--recommendation-id", type=int, required=True)
    feedback_parser.add_argument("--feedback-type", required=True)
    feedback_parser.add_argument("--note", default="")
    return parser


def _print_payload(payload: dict[str, object]) -> None:
    sys.stdout.write(f"{json.dumps(payload, ensure_ascii=False)}\n")


async def _run_command(args: argparse.Namespace, adapter: Any) -> dict[str, object]:
    if args.command == "doctor":
        skills = build_openclaw_skills(adapter)
        return {
            "ok": True,
            "data": {
                "skill_pack_path": str(_SKILL_PACK_PATH),
                "skill_pack_exists": _SKILL_PACK_PATH.exists(),
                "skill_count": len(skills),
                "skill_names": [item.name for item in skills],
                "cli_module": "openbiliclaw.integrations.openclaw.cli",
            },
        }
    if args.command == "emit-skill-descriptors":
        skills = build_openclaw_skills(adapter)
        return {
            "ok": True,
            "data": {
                "skills": [
                    {
                        "name": item.name,
                        "description": item.description,
                        "input_schema": item.input_schema,
                    }
                    for item in skills
                ]
            },
        }
    try:
        if args.command == "sync-account":
            result = await adapter.sync_account()
        elif args.command == "get-profile":
            result = await adapter.get_profile()
        elif args.command == "runtime-status":
            result = await adapter.get_runtime_status()
        elif args.command == "recommend":
            result = await adapter.recommend(
                limit=args.limit,
                refresh_if_needed=bool(args.refresh_if_needed),
            )
        elif args.command == "submit-feedback":
            request = FeedbackRequest(
                recommendation_id=args.recommendation_id,
                feedback_type=args.feedback_type,
                note=args.note,
            )
            result = await adapter.submit_feedback(request)
        else:  # pragma: no cover - argparse guarantees command validity
            raise AdapterValidationError(f"Unsupported command: {args.command}")
    except AdapterValidationError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "error_type": "validation_error",
        }
    except AdapterOperationError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "error_type": "operation_error",
        }
    return {
        "ok": True,
        "data": asdict(result),
    }


def main(argv: Sequence[str] | None = None, *, adapter: Any | None = None) -> int:
    """Run the OpenClaw adapter CLI and print JSON output."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if adapter is not None:
        resolved_adapter = adapter
    elif args.command in {"doctor", "emit-skill-descriptors"}:
        resolved_adapter = object()
    else:
        resolved_adapter = build_openclaw_adapter()
    payload = asyncio.run(_run_command(args, resolved_adapter))
    _print_payload(payload)
    return 0 if bool(payload.get("ok", False)) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

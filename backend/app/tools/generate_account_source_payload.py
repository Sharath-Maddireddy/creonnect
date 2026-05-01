from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from backend.app.account_sources import materialize_account_source_payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate normalized account payload from a shared source.")
    parser.add_argument("--source", required=True, choices=["fixture", "creonnect_bd"])
    parser.add_argument("--account-id", default=None)
    parser.add_argument("--username", default=None)
    parser.add_argument("--bio", default=None)
    parser.add_argument("--follower-count", type=int, default=None)
    parser.add_argument("--creator-dominant-category", default=None)
    parser.add_argument("--fixture-path", default=None)
    parser.add_argument("--connection-id", default=None)
    parser.add_argument("--bd-base-url", default=None)
    parser.add_argument("--post-limit", type=int, default=30)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    payload = await materialize_account_source_payload(
        {
            "source": args.source,
            "account_id": args.account_id,
            "username": args.username,
            "bio": args.bio,
            "follower_count": args.follower_count,
            "creator_dominant_category": args.creator_dominant_category,
            "fixture_path": args.fixture_path,
            "connection_id": args.connection_id,
            "bd_base_url": args.bd_base_url,
            "post_limit": args.post_limit,
        },
        post_limit=args.post_limit,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n", encoding="utf-8")
    print(f"Wrote normalized payload to {out_path}")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()

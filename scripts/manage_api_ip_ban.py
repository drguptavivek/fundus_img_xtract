"""Inspect or clear an API abuse ban without loading the app or patient database."""
from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redis

from app_init.api_abuse import api_abuse_keys, BAN_INDEX_KEY
from utils.env_loader import load_environment
from utils.redis_connection import build_redis_url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ip", type=ipaddress.ip_address)
    parser.add_argument("--clear", action="store_true", help="Clear both the ban and failure window")
    args = parser.parse_args()
    load_environment()
    client = redis.Redis.from_url(build_redis_url(), socket_connect_timeout=2, socket_timeout=2)
    failure_key, ban_key = api_abuse_keys(str(args.ip))
    if args.clear:
        client.delete(failure_key, ban_key)
        client.zrem(BAN_INDEX_KEY, str(args.ip))
    print(json.dumps({"ip": str(args.ip), "ban_seconds_remaining": max(0, client.ttl(ban_key)),
                      "failures": int(client.get(failure_key) or 0), "cleared": args.clear}))


if __name__ == "__main__":
    main()

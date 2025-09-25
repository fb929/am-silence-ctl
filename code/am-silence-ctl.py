#!/usr/bin/env python3
"""
Script to create or delete silences in Alertmanager via API.

Features:
- `createdBy` is taken from the USER environment variable for creation
- `comment` is optional via -c/--comment for creation
- `-r/--role [VALUE]` flag adds a matcher {"name":"role","value":<role>,"isRegex":false}
   * If VALUE is omitted, use the default from config
- `-g/--group [VALUE]` flag adds a matcher {"name":"group","value":<group>,"isRegex":false}
   * If VALUE is omitted, use the default from config
- If `--alertname` is omitted and no other matcher is provided, a matcher
  {"name":"fqdn","value":<socket.getfqdn()>,"isRegex":false} is used by default
- `-d/--delete` enables deletion mode
- `--dry-run` prints what would be created/deleted without making any API calls
- YAML config supports:
    alertmanager_url (string, base URL)
    role (string, optional)
    group (string, optional)
"""

import os
import sys
import json
import argparse
import datetime
import requests
import logging
import socket
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from pathlib import Path

DEFAULT_AM_URL = "http://127.0.0.1:9093"
DEFAULT_CONFIG_LOCATIONS = [
    "/etc/am-silence-ctl/config.yaml",
    str(Path.home() / ".am-silence-ctl.yaml"),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def load_config(path: Optional[str]) -> Dict[str, Any]:
    """Load config (alertmanager_url, role, group) from YAML."""
    cfg: Dict[str, Any] = {"alertmanager_url": DEFAULT_AM_URL}

    locations = [path] if path else DEFAULT_CONFIG_LOCATIONS

    try:
        import yaml  # type: ignore
    except Exception:
        logger.warning("PyYAML not available; using defaults (no role/group, default URL).")
        return cfg

    for loc in locations:
        p = Path(loc).expanduser()
        if not p.is_file():
            continue
        try:
            with p.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            am_url = data.get("alertmanager_url")
            role = data.get("role")
            group = data.get("group")

            if am_url:
                parsed = urlparse(am_url)
                if parsed.scheme and parsed.netloc:
                    cfg["alertmanager_url"] = am_url.rstrip("/")
                else:
                    logger.error("Invalid 'alertmanager_url' in %s: %s (ignored)", p, am_url)
            if role:
                cfg["role"] = str(role)
            if group:
                cfg["group"] = str(group)

            logger.info("Loaded config from %s", p)
            break
        except Exception as e:
            logger.error("Failed to read config %s: %s", p, e)

    return cfg


def am_endpoints(base_url: str) -> Dict[str, str]:
    """Build v2 endpoints from base URL."""
    base = base_url.rstrip("/")
    api = base if base.endswith("/api/v2") else base + "/api/v2"
    return {
        "silences": f"{api}/silences",
        "silence": f"{api}/silence",  # + /<id>
    }


def build_matchers(args: argparse.Namespace, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build matchers list from CLI args and config."""
    matchers: List[Dict[str, Any]] = []

    if args.alertname:
        matchers.append({"name": "alertname", "value": args.alertname, "isRegex": False})
        logger.info("Added matcher alertname=%s", args.alertname)

    # Handle role
    if args.role is not None:
        if args.role is True:  # flag used without value
            role_value = cfg.get("role")
        else:
            role_value = args.role
        if not role_value:
            logger.error("--role was requested but no value provided (and no config default)")
            sys.exit(1)
        matchers.append({"name": "role", "value": role_value, "isRegex": False})
        logger.info("Added matcher role=%s", role_value)

    # Handle group
    if args.group is not None:
        if args.group is True:  # flag used without value
            group_value = cfg.get("group")
        else:
            group_value = args.group
        if not group_value:
            logger.error("--group was requested but no value provided (and no config default)")
            sys.exit(1)
        matchers.append({"name": "group", "value": group_value, "isRegex": False})
        logger.info("Added matcher group=%s", group_value)

    if not matchers:
        fqdn_value = socket.getfqdn()
        if not fqdn_value:
            logger.error("No matchers provided and FQDN is empty/unknown")
            sys.exit(1)
        matchers.append({"name": "fqdn", "value": fqdn_value, "isRegex": False})
        logger.info("Added matcher fqdn=%s", fqdn_value)

    return matchers


def silence_matches_input(silence: Dict[str, Any], input_matchers: List[Dict[str, Any]]) -> bool:
    """Check if silence includes all input matchers (subset match on name/value/isRegex)."""
    s_matchers = silence.get("matchers", []) or []
    s_set = {(m.get("name"), m.get("value"), bool(m.get("isRegex"))) for m in s_matchers}
    i_set = {(m.get("name"), m.get("value"), bool(m.get("isRegex"))) for m in input_matchers}
    return i_set.issubset(s_set)


def list_active_silences(urls: Dict[str, str]) -> List[Dict[str, Any]]:
    """Fetch active silences."""
    try:
        resp = requests.get(urls["silences"], timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to list silences: %s", e)
        sys.exit(1)
    silences = resp.json()
    return [s for s in silences if (s.get("status", {}) or {}).get("state") == "active"]


def delete_silence(urls: Dict[str, str], silence_id: str, dry_run: bool) -> bool:
    """Delete silence by ID."""
    url = f"{urls['silence']}/{silence_id}"
    if dry_run:
        logger.info("[dry-run] Would delete silence id=%s", silence_id)
        return True
    try:
        resp = requests.delete(url, timeout=10)
        if resp.ok:
            logger.info("Deleted silence id=%s", silence_id)
            return True
        logger.error("Failed to delete id=%s: %s %s", silence_id, resp.status_code, resp.text)
        return False
    except requests.RequestException as e:
        logger.error("Network error deleting id=%s: %s", silence_id, e)
        return False


def create_silence(urls: Dict[str, str], matchers: List[Dict[str, Any]],
                   created_by: str, hours: int, comment: str, dry_run: bool) -> None:
    """Create silence."""
    start = datetime.datetime.utcnow()
    end = start + datetime.timedelta(hours=hours)
    payload = {
        "matchers": matchers,
        "startsAt": start.isoformat("T") + "Z",
        "endsAt": end.isoformat("T") + "Z",
        "createdBy": created_by,
        "comment": comment or f"Silence created by {created_by}"
    }
    headers = {"Content-Type": "application/json"}

    logger.info("Prepared request: url='%s'; data=%s", urls["silences"], json.dumps(payload, indent=2))

    if dry_run:
        logger.info("[dry-run] Would create a silence; no request sent.")
        return

    try:
        resp = requests.post(urls["silences"], headers=headers, data=json.dumps(payload), timeout=10)
    except requests.RequestException as e:
        logger.error("Network error: %s", e)
        sys.exit(1)

    if resp.ok:
        silence_id = (resp.json().get("silenceID")
                      if resp.headers.get("Content-Type", "").startswith("application/json")
                      else None)
        logger.info("Silence created successfully: %s", silence_id or resp.text)
    else:
        logger.error("Error %s: %s", resp.status_code, resp.text)
        sys.exit(1)


def delete_matching_silences(urls: Dict[str, str], matchers: List[Dict[str, Any]], dry_run: bool) -> None:
    """Delete silences matching input matchers."""
    active = list_active_silences(urls)
    to_delete = [s for s in active if silence_matches_input(s, matchers)]

    if not to_delete:
        logger.info("No active silences matched the provided matchers. Nothing to delete.")
        return

    logger.info("Matched %d silence(s) for deletion", len(to_delete))
    for s in to_delete:
        sid = s.get("id") or s.get("silenceID")
        if not sid:
            logger.warning("Skipping silence without id: %s", s)
            continue
        delete_silence(urls, sid, dry_run)


def main():
    parser = argparse.ArgumentParser(description="Create or delete an Alertmanager silence via API")
    parser.add_argument("-c", "--comment", help="Optional comment (create mode only)", default="")
    parser.add_argument("--hours", type=int, default=2, help="Silence duration in hours (create mode, default: 2)")
    parser.add_argument("--alertname", help="Value for the 'alertname' label (optional)")
    parser.add_argument(
        "-r", "--role",
        nargs="?",
        const=True,
        help="Include 'role' matcher (from config if no value is given, or custom value)"
    )
    parser.add_argument(
        "-g", "--group",
        nargs="?",
        const=True,
        help="Include 'group' matcher (from config if no value is given, or custom value)"
    )
    parser.add_argument("-d", "--delete", action="store_true", help="Delete mode")
    parser.add_argument("--dry-run", action="store_true", help="Do not call the API; only print what would be done")
    parser.add_argument("--config", help=f"YAML config path (default search: {', '.join(DEFAULT_CONFIG_LOCATIONS)})")

    args = parser.parse_args()

    cfg = load_config(args.config)
    base_url = cfg.get("alertmanager_url", DEFAULT_AM_URL)
    endpoints = am_endpoints(base_url)

    matchers = build_matchers(args, cfg)

    if args.delete:
        delete_matching_silences(endpoints, matchers, args.dry_run)
    else:
        created_by = os.getenv("USER", "unknown")
        create_silence(endpoints, matchers, created_by, args.hours, args.comment, args.dry_run)


if __name__ == "__main__":
    main()

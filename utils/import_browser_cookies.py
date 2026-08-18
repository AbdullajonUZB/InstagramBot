"""Convert browser-exported JSON cookies to the Netscape format used by yt-dlp."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ALLOWED_DOMAINS = ("instagram.com", "facebook.com", "fb.watch")


def convert(input_path: Path, output_path: Path):
    cookies = json.loads(input_path.read_text(encoding="utf-8"))
    unique = {}

    for cookie in cookies:
        domain = str(cookie.get("domain", "")).lower().lstrip(".")
        if not any(domain == allowed or domain.endswith(f".{allowed}") for allowed in ALLOWED_DOMAINS):
            continue

        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue

        key = (cookie.get("domain", ""), cookie.get("path", "/"), name)
        current = unique.get(key)
        if current is None or float(cookie.get("expirationDate") or 0) >= float(current.get("expirationDate") or 0):
            unique[key] = cookie

    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated from a browser cookie export. Keep this file private.",
    ]
    for cookie in sorted(unique.values(), key=lambda item: (item.get("domain", ""), item.get("name", ""))):
        domain = cookie.get("domain", "")
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = cookie.get("path") or "/"
        secure = "TRUE" if cookie.get("secure") else "FALSE"
        expiration = int(float(cookie.get("expirationDate") or 0))
        lines.append(
            "\t".join(
                [
                    domain,
                    include_subdomains,
                    path,
                    secure,
                    str(expiration),
                    str(cookie["name"]),
                    str(cookie["value"]),
                ]
            )
        )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(unique)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(f"Imported {convert(args.input, args.output)} cookies")

#!/usr/bin/env python3
"""Creator Image Editor handover demo.

Submits the same source image through a "trending" style (bold, fully
committed transformation) and a "brand-production" style (subtle,
campaign-safe adjustment) so the difference in prompt strategy is visible
side by side. Downloads both results locally.

Stdlib-only (no extra pip installs needed) so any teammate with the repo's
venv can run it as-is.

Usage:
    # 1. Start the backend (from repo root):
    #    .venv/Scripts/python.exe -m uvicorn backend.main:app --reload --port 8000
    #    Make sure backend/.env has DEV_AUTH_BYPASS=1 for local testing without
    #    real Instagram login (see docs/IMAGE_EDITOR_HANDOVER.md).

    # 2. Run the demo:
    python scripts/demo_image_editor.py --image path/to/photo.jpg

    # Optional:
    python scripts/demo_image_editor.py --image photo.jpg \\
        --trending-style y2k_digicam --brand-style brand_kit_color_match \\
        --base-url http://localhost:8000 --out-dir demo_results
"""

from __future__ import annotations

import argparse
import io
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TRENDING_STYLE = "lofi_dusk"
DEFAULT_BRAND_STYLE = "relight"
POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 90


def _multipart_body(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    buf = io.BytesIO()

    def write(text: str) -> None:
        buf.write(text.encode("utf-8"))

    for name, value in fields.items():
        write(f"--{boundary}\r\n")
        write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n')
        write(f"{value}\r\n")

    mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    write(f"--{boundary}\r\n")
    write(f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n')
    write(f"Content-Type: {mime_type}\r\n\r\n")
    buf.write(file_path.read_bytes())
    write("\r\n")
    write(f"--{boundary}--\r\n")

    return buf.getvalue(), boundary


def submit_job(base_url: str, image_path: Path, style_id: str, goal_id: str = "post") -> str:
    fields = {
        "goal_id": goal_id,
        "style_id": style_id,
        "event_id": "none",
        "enhancement_ids": "[]",
        "output_format": "png",
    }
    body, boundary = _multipart_body(fields, "image", image_path)
    idempotency_key = f"handover-demo-{style_id}-{uuid.uuid4().hex[:8]}"

    request = urllib.request.Request(
        f"{base_url}/api/v1/creator/image-editor/jobs",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Idempotency-Key": idempotency_key,
        },
    )
    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read())
    return str(payload["id"])


def poll_job(base_url: str, job_id: str) -> dict:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        request = urllib.request.Request(f"{base_url}/api/v1/creator/image-editor/jobs/{job_id}")
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read())
        status = payload.get("status")
        print(f"    status: {status}")
        if status in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Job {job_id} did not finish within {POLL_TIMEOUT_SECONDS}s")


def download_asset(base_url: str, asset_url_path: str, destination: Path) -> None:
    request = urllib.request.Request(f"{base_url}{asset_url_path}")
    with urllib.request.urlopen(request) as response:
        destination.write_bytes(response.read())


def run_one(base_url: str, image_path: Path, style_id: str, category_label: str, out_dir: Path) -> None:
    print(f"\n[{category_label}] style={style_id!r} - submitting job...")
    job_id = submit_job(base_url, image_path, style_id)
    print(f"    job_id: {job_id}")
    result = poll_job(base_url, job_id)

    if result.get("status") != "succeeded":
        print(f"    FAILED: {result.get('error')}")
        return

    result_url = result.get("result_url")
    if not result_url:
        print("    FAILED: no result_url in response")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    destination = out_dir / f"{style_id}_result.png"
    download_asset(base_url, result_url, destination)
    print(f"    saved: {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", required=True, type=Path, help="Path to a source photo to run through both styles")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Backend base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--trending-style", default=DEFAULT_TRENDING_STYLE, help=f"A 'trending' style id (default: {DEFAULT_TRENDING_STYLE})")
    parser.add_argument("--brand-style", default=DEFAULT_BRAND_STYLE, help=f"A 'brand-production' style id (default: {DEFAULT_BRAND_STYLE})")
    parser.add_argument("--out-dir", default=Path("demo_results"), type=Path, help="Where to save result images (default: ./demo_results)")
    args = parser.parse_args()

    if not args.image.exists():
        print(f"Image not found: {args.image}", file=sys.stderr)
        return 1

    print("Creator Image Editor handover demo")
    print(f"  backend:  {args.base_url}")
    print(f"  source:   {args.image}")
    print(f"  trending: {args.trending_style}  (expect a bold, reinterpreted result)")
    print(f"  brand:    {args.brand_style}  (expect a subtle, conservative result)")

    try:
        run_one(args.base_url, args.image, args.trending_style, "trending", args.out_dir)
        run_one(args.base_url, args.image, args.brand_style, "brand-production", args.out_dir)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"\nHTTP {exc.code} from backend: {body}", file=sys.stderr)
        if exc.code == 401:
            print(
                "Not authenticated. For local testing, set DEV_AUTH_BYPASS=1 in backend/.env "
                "(non-production only) - see docs/IMAGE_EDITOR_HANDOVER.md section 4.",
                file=sys.stderr,
            )
        return 1
    except urllib.error.URLError as exc:
        print(f"\nCould not reach backend at {args.base_url}: {exc}", file=sys.stderr)
        print("Is the backend running? uvicorn backend.main:app --reload --port 8000", file=sys.stderr)
        return 1

    print(f"\nDone. Compare the two results in {args.out_dir}/ against {args.image}.")
    print("Expect: trending = visibly reinterpreted scene/lighting; brand = same shot, subtle grade only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

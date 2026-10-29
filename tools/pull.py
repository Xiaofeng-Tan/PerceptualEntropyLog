"""Download every run of a SwanLab cloud project into a raw (NOT sanitized) dump.

Scalars, system metrics, config/metadata and console logs are pulled; media
(images, videos) are intentionally skipped.

Usage:
    SWANLAB_API_KEY=... python pull.py <workspace>/<project>[/<run id>] <raw_dir>

With a run id only that run is pulled; otherwise every run of the project.

The raw dump contains un-sanitized data; keep it out of the repository and run
sanitize.py on it before sharing anything.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

import swanlab


def fetch_scalars(exp, keys):
    """Return {key: [{step, value, timestamp}, ...]} with full resolution."""
    out = {}
    for i in range(0, len(keys), 10):
        resp = exp.metrics(keys[i : i + 10], all=True)
        for item in resp.get("list", []):
            out[item["key"]] = item["metrics"]
    return out


def pull_run(exp, root):
    run_dir = root / exp.name
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{exp.name}] meta", flush=True)

    meta = {k: v for k, v in exp.json().items() if k not in ("profile",)}
    meta["profile"] = exp.profile
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False, default=str))

    custom = [k.key for k in exp.series("SCALAR", "CUSTOM")]
    system = [k.key for k in exp.series("SCALAR", "SYSTEM")]
    print(f"[{exp.name}] scalars: {len(custom)} custom, {len(system)} system", flush=True)
    (run_dir / "scalars.json").write_text(json.dumps(fetch_scalars(exp, custom)))
    (run_dir / "system.json").write_text(json.dumps(fetch_scalars(exp, system)))

    print(f"[{exp.name}] console log", flush=True)
    start, chunks = 0, []
    while True:
        resp = exp.export_logs(start=start, rows=500_000)
        with urllib.request.urlopen(resp.data["url"], timeout=600) as r:
            text = r.read().decode("utf-8", "replace")
        chunks.append(text)
        n = text.count("\n")
        if n < 500_000:
            break
        start += n
    (run_dir / "console.log").write_text("".join(chunks))


def main():
    path, raw_dir = sys.argv[1], Path(sys.argv[2])
    api = swanlab.Api(api_key=os.environ["SWANLAB_API_KEY"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    runs = [api.run(path)] if path.count("/") == 2 else api.runs(path)
    for exp in runs:
        pull_run(exp, raw_dir)


if __name__ == "__main__":
    main()

"""Rebuild a SwanLab local-mode log directory from the sanitized dump.

Usage:
    python rebuild.py <clean_dir> <swanlog_dir> [project_name]

Each sanitized run becomes one local SwanLab experiment containing its config,
all custom scalars (original step axis), system metrics under ``system/``,
images with captions, and the console log. Hardware/runtime probes and the
system monitor of the current machine are disabled so nothing about the
machine running this script is recorded.
"""
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import swanlab

PROBES_OFF = {
    "hardware": False,
    "runtime": False,
    "requirements": False,
    "git": False,
    "swanlab": False,
    "conda": False,
    "monitor": False,
}


def by_step(series, prefix=""):
    rows = defaultdict(dict)
    for key, points in series.items():
        for p in points:
            rows[p["step"]][prefix + key] = p["value"]
    return rows


def rebuild_run(run_dir, log_dir, project):
    info = json.loads((run_dir / "run.json").read_text())
    config = json.loads((run_dir / "config.json").read_text())
    # step-aligned versions written by align_steps.py take precedence
    aligned = (run_dir / "scalars_aligned.json").exists()
    scalars = json.loads((run_dir / ("scalars_aligned.json" if aligned else "scalars.json")).read_text())
    system = json.loads((run_dir / "system.json").read_text())
    media_file = run_dir / ("media_aligned.json" if aligned else "media.json")
    media = json.loads(media_file.read_text()) if media_file.exists() else {}
    description = f"state on cloud: {info['state']}; created {info['created_at']}"
    if aligned:
        a = json.loads((run_dir / "alignment.json").read_text())
        how = (f"{a['rollouts_per_reference_step']:.3f} rollouts per step (samples)"
               if a["mode"] == "samples" else f"rollout step / {a['factor']:g}")
        description += f"; step axis aligned to reference: {how}"

    settings = swanlab.Settings(mode="local", probe=PROBES_OFF, terminal={"proxy_type": "none"})
    run = swanlab.init(
        project=project,
        name=info["name"],
        description=description,
        config=config,
        log_dir=str(log_dir),
        settings=settings,
        reinit=True,
    )

    rows = by_step(scalars)
    for key, entries in media.items():
        for e in entries:
            rows[e["step"]][key] = [
                (swanlab.Video if it["file"].endswith(".gif") else swanlab.Image)(
                    str(run_dir / it["file"]), caption=it.get("caption"))
                for it in e["items"]
            ]
    for step in sorted(rows):
        swanlab.log(rows[step], step=step)

    # system metrics keep their own (monitor tick) step axis
    sys_rows = by_step({k.replace("__swanlab__.", ""): v for k, v in system.items()}, prefix="system/")
    for step in sorted(sys_rows):
        swanlab.log(sys_rows[step], step=step)

    out_dir = Path(run.dir)
    swanlab.finish()

    # The terminal proxy drops lines at this throughput, so the console log is
    # written straight into the run's console dir (swanboard reads YYYY-MM-DD.log).
    console_dir = out_dir / "console"
    console_dir.mkdir(exist_ok=True)
    for f in console_dir.iterdir():
        f.unlink()
    shutil.copyfile(run_dir / "console.log", console_dir / f"{info['created_at'][:10]}.log")
    shutil.rmtree(out_dir / "debug", ignore_errors=True)


def main():
    clean, log_dir = Path(sys.argv[1]), Path(sys.argv[2])
    project = sys.argv[3] if len(sys.argv) > 3 else "flux_pec_ddpo"
    runs = sorted((p for p in clean.iterdir() if (p / "run.json").exists()),
                  key=lambda p: json.loads((p / "run.json").read_text())["created_at"])
    for run_dir in runs:
        print(f"rebuild {run_dir.name}", file=sys.stderr, flush=True)
        rebuild_run(run_dir, log_dir, project)


if __name__ == "__main__":
    main()

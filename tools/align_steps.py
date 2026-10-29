"""Align a run trained with a different batch size to a reference run's step axis.

Usage:
    python align_steps.py <run_dir> <reference_run_dir>            # adaptive (by samples)
    python align_steps.py <run_dir> <reference_run_dir> --factor 11  # fixed ratio

<run_dir> is a sanitized run whose SwanLab step is a global log counter and
whose training step is logged as ``rollout/step`` (``eval/step`` for eval
keys). The reference run is logged directly against its rollout step.

Adaptive mode (default) maps rollout r of the run to
    equivalent step = cumulative rollout/num_samples up to r
                      / median rollout/num_samples per reference step,
so both runs are compared at equal numbers of training samples, and adapts
automatically if the batch size changes during the run. With --factor F the
equivalent step is simply r / F.

Resumes from an earlier checkpoint (rollout/step decreasing) are handled by
dropping points of the abandoned segment whose rollout is re-run afterwards.
Likewise, when checkpoints are re-evaluated later (eval/step decreasing), the
later evaluations replace earlier eval points from the same rollout onwards.

Equivalent steps are rounded to integers; scalars falling into the same
integer step are averaged (counters such as */step keep the last value),
and media keep the last entry. Writes scalars_aligned.json,
media_aligned.json and alignment.json next to the originals; rebuild.py
prefers the aligned files when present.
"""
import argparse
import bisect
import json
import statistics
from collections import defaultdict
from pathlib import Path

STEP_KEYS = ("rollout/step", "eval/step")


def last_value_before(points):
    """Return f(global_step) -> value of the last point logged at or before it."""
    xs = [p["step"] for p in points]
    vs = [p["value"] for p in points]

    def f(g):
        i = bisect.bisect_right(xs, g) - 1
        return vs[i] if i >= 0 else None

    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("reference_run_dir", type=Path)
    ap.add_argument("--factor", type=float, help="fixed ratio: equivalent step = rollout step / factor")
    args = ap.parse_args()

    scalars = json.loads((args.run_dir / "scalars.json").read_text())
    media = json.loads((args.run_dir / "media.json").read_text()) if (args.run_dir / "media.json").exists() else {}
    rollout_of = last_value_before(scalars["rollout/step"])
    eval_of = last_value_before(scalars["eval/step"])

    # (global step where a counter went back, first value after it): a training
    # resume on rollout/step, or a later re-evaluation of checkpoints on eval/step
    def backjumps(points):
        return [(points[i]["step"], points[i]["value"]) for i in range(1, len(points))
                if points[i]["value"] < points[i - 1]["value"]]

    resumes = backjumps(scalars["rollout/step"])
    re_evals = backjumps(scalars["eval/step"])

    def rollout(key, g):
        is_eval = key.startswith("eval/")
        r = eval_of(g) if is_eval else rollout_of(g)
        if r is not None and any(g < g_res and r >= r_res for g_res, r_res in (re_evals if is_eval else resumes)):
            return None  # superseded by the later segment
        return r

    ref = json.loads((args.reference_run_dir / "scalars.json").read_text())
    ref_samples = statistics.median(p["value"] for p in ref["rollout/num_samples"])

    if args.factor:
        def equivalent(r):
            return r / args.factor
        info = {"mode": "factor", "factor": args.factor}
    else:
        per_rollout = {}
        for p in scalars["rollout/num_samples"]:
            r = rollout("rollout/num_samples", p["step"])
            if r is not None:
                per_rollout[r] = p["value"]
        rs = sorted(per_rollout)
        cum, acc = [], 0.0
        for r in rs:
            acc += per_rollout[r]
            cum.append(acc)

        def equivalent(r):
            if r is None or r <= 0:
                return 0.0
            i = bisect.bisect_right(rs, r) - 1
            return (cum[i] if i >= 0 else 0.0) / ref_samples

        run_samples = statistics.median(per_rollout.values())
        info = {
            "mode": "samples",
            "run_samples_per_step": run_samples,
            "reference_samples_per_step": ref_samples,
            "rollouts_per_reference_step": ref_samples / run_samples,
        }

    aligned = {}
    for key, points in scalars.items():
        bins = defaultdict(list)
        for p in points:
            r = rollout(key, p["step"])
            if r is not None:
                bins[round(equivalent(r))].append(p)
        out = []
        for step in sorted(bins):
            ps = bins[step]
            last = key in STEP_KEYS or key.endswith("/step")
            value = ps[-1]["value"] if last else sum(p["value"] for p in ps) / len(ps)
            out.append({"step": step, "value": value, "timestamp": ps[-1].get("timestamp")})
        aligned[key] = out

    aligned_media = {}
    for key, entries in media.items():
        by_step = {}
        for e in entries:
            r = rollout(key, e["step"])
            if r is not None:
                by_step[round(equivalent(r))] = e["items"]
        aligned_media[key] = [{"step": s, "items": by_step[s]} for s in sorted(by_step)]

    last_rollout = scalars["rollout/step"][-1]["value"]
    info.update({
        "source_axis": "rollout/step (eval/step for eval/* keys)",
        "last_rollout_step": last_rollout,
        "resumes": [{"global_step": g, "resumed_at_rollout": r} for g, r in resumes],
        "re_evaluations": [{"global_step": g, "from_rollout": r} for g, r in re_evals],
        "last_equivalent_step": round(equivalent(last_rollout)),
    })
    (args.run_dir / "scalars_aligned.json").write_text(json.dumps(aligned))
    if aligned_media:
        (args.run_dir / "media_aligned.json").write_text(json.dumps(aligned_media, indent=1, ensure_ascii=False))
    (args.run_dir / "alignment.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()

"""Sanitize a raw dump produced by pull.py.

Usage:
    python sanitize.py <raw_dir> <clean_dir>

Removes user names, cluster storage paths, host names, PIDs, IPs, e-mails,
tokens, cloud run ids and signed URLs. Everything written to <clean_dir> is
safe to share; <raw_dir> is not.
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

# Private terms (user names, cluster/host names, ...) are never stored in this
# file; pass them at runtime as a comma-separated list in SANITIZE_TERMS.
# The API key in SWANLAB_API_KEY is redacted as well.
PRIVATE_TERMS = [t.strip() for t in os.environ.get("SANITIZE_TERMS", "").split(",") if t.strip()]
if os.environ.get("SWANLAB_API_KEY"):
    PRIVATE_TERMS.append(os.environ["SWANLAB_API_KEY"])

# Order matters: URLs before paths, paths before bare terms.
RULES = [
    (re.compile(r"https?://swanlab\.cn/@[^\s\"']*"), "<SWANLAB_URL>"),
    (re.compile(r"https?://[^\s\"']*myqcloud\.com[^\s\"']*"), "<SIGNED_URL>"),
    (re.compile(r"\b(?:hf|sk|ghp|gho|github_pat)_[A-Za-z0-9_]{16,}\b"), "<TOKEN>"),
    (re.compile(r"\bAKID[A-Za-z0-9]{16,}\b"), "<TOKEN>"),
    # SwanLab run references such as <owner>/<project>/<run id>
    (re.compile(r"(?<![\w/<>.:-])[\w.-]+/[\w.-]+/[a-z0-9]{8}\b"), "<SWANLAB_RUN>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z][\w.-]*"), "<EMAIL>"),
    # IPv4; skip version pins such as pkg==12.4.5.8
    (re.compile(r"(?<![\w.])(?<!==)(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), "<IP>"),
    # absolute paths: keep only the last component, e.g. /a/b/c/flux -> <PATH>/flux
    (re.compile(r"(?<![\w:/.<>-])/(?:[\w.@+-]+/)+(?=[\w.@+-]*)"), "<PATH>/"),
    (re.compile(r"swanlog/run-\d{8}_\d{6}-\w+"), "swanlog/<RUN_DIR>"),
    (re.compile(r"\b\d{8}_\d{6}-[a-z0-9]{8}\b"), "<RUN_DIR>"),
] + [(re.compile(re.escape(t), re.I), "<REDACTED>") for t in PRIVATE_TERMS]

# Anything matching these after sanitization is treated as a leak.
LEAK_CHECK = re.compile(
    "|".join([r"/Users/", r"/home/", r"/root/", r"myqcloud", r"\bAKID"] + [re.escape(t) for t in PRIVATE_TERMS]),
    re.I,
)


def scrub(text):
    for pat, repl in RULES:
        text = pat.sub(repl, text)
    return text


def scrub_obj(obj):
    if isinstance(obj, str):
        return scrub(obj)
    if isinstance(obj, list):
        return [scrub_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub_obj(v) for k, v in obj.items()}
    return obj


def plain_config(cfg):
    """SwanLab cloud wraps config values as {desc, sort, value}; unwrap them in order."""
    items = sorted(cfg.items(), key=lambda kv: kv[1].get("sort", 0) if isinstance(kv[1], dict) else 0)
    return {k: (v["value"] if isinstance(v, dict) and "value" in v else v) for k, v in items}


def environment(meta):
    """Keep only non-identifying environment info."""
    md = meta["profile"].get("metadata") or {}
    rt = md.get("runtime") or {}
    hw = md.get("hardware") or {}
    accel = []
    for a in hw.get("accelerators") or []:
        names = [d["name"] for d in a.get("devices", [])]
        accel.append({
            "vendor": a.get("vendor"),
            "count": len(names),
            "devices": sorted(set(names)),
            "memory_gb_each": (a.get("devices") or [{}])[0].get("memory"),
            "cuda_version": a.get("cuda_version"),
        })
    command = rt.get("command") or ""
    command = re.sub(r"^\S*python[\d.]*", "python", command)
    return scrub_obj({
        "os": rt.get("os_pretty"),
        "python_version": rt.get("python_version"),
        "command": command,
        "cpu_logical_count": (hw.get("cpu") or {}).get("logical_count"),
        "memory_gb": (hw.get("memory") or {}).get("total"),
        "accelerators": accel,
        "swanlab_version_at_training": (md.get("swanlab") or {}).get("version"),
    })


def sanitize_run(src, dst):
    meta = json.loads((src / "meta.json").read_text())
    dst.mkdir(parents=True, exist_ok=True)

    run_info = scrub_obj({
        "name": meta["name"],
        "state": meta.get("state"),
        "description": meta.get("description"),
        "group": meta.get("group"),
        "job_type": meta.get("job_type"),
        "labels": [l.get("name") for l in meta.get("labels") or []],
        "created_at": meta.get("created_at"),
        "finished_at": meta.get("finished_at"),
    })
    (dst / "run.json").write_text(json.dumps(run_info, indent=1, ensure_ascii=False))
    config = scrub_obj(plain_config(meta["profile"].get("config") or {}))
    (dst / "config.json").write_text(json.dumps(config, indent=1, ensure_ascii=False))
    (dst / "environment.json").write_text(json.dumps(environment(meta), indent=1, ensure_ascii=False))
    req = meta["profile"].get("requirements") or ""
    (dst / "requirements.txt").write_text(scrub(req if isinstance(req, str) else "\n".join(req)))

    # scalars: keep step/value/timestamp, drop nothing else (no identifying data)
    for name in ("scalars.json", "system.json"):
        shutil.copyfile(src / name, dst / name)

    media = json.loads((src / "media.json").read_text()) if (src / "media.json").exists() else {}
    for entries in media.values():
        for e in entries:
            for it in e["items"]:
                it["caption"] = scrub(it["caption"]) if it.get("caption") else it.get("caption")
                out = dst / it["file"]
                out.parent.mkdir(parents=True, exist_ok=True)
                if not out.exists():
                    os.link(src / it["file"], out)  # hardlink: images carry no metadata to scrub
    if media:
        (dst / "media.json").write_text(json.dumps(media, indent=1, ensure_ascii=False))

    with open(src / "console.log", encoding="utf-8", errors="replace") as fi, open(
        dst / "console.log", "w", encoding="utf-8"
    ) as fo:
        in_run_dir = False  # SwanLab wraps the run dir over several lines at arbitrary points
        for line in fi:
            if in_run_dir and not line.startswith("swanlab:"):
                continue
            if in_run_dir:
                fo.write("<PATH>/<RUN_DIR>\n")
            in_run_dir = line.rstrip().endswith("Run data saved at")
            fo.write(scrub(line))


def check_leaks(root):
    bad = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in (".json", ".log", ".txt", ".yaml", ".md"):
            for i, line in enumerate(p.open(encoding="utf-8", errors="replace")):
                m = LEAK_CHECK.search(line)
                if m:
                    bad.append(f"{p}:{i + 1}: {m.group(0)!r}")
                    break
    return bad


def main():
    raw, clean = Path(sys.argv[1]), Path(sys.argv[2])
    for src in sorted(p for p in raw.iterdir() if (p / "meta.json").exists()):
        print("sanitize", src.name, flush=True)
        sanitize_run(src, clean / scrub(src.name))
    leaks = check_leaks(clean)
    if leaks:
        print("POSSIBLE LEAKS:\n" + "\n".join(leaks))
        sys.exit(1)
    print("no leaks found")


if __name__ == "__main__":
    main()

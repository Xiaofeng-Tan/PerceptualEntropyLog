"""Hide and rename runs in both the sanitized dump and the local swanlog.

Usage:
    python rename.py <display_names.json> <runs_dir> <swanlog_dir> <backup_dir>

display_names.json: {"hide": [old_name, ...], "rename": {old_name: new_name}}
Hidden runs are moved to <backup_dir> (keep it outside the repository).
Old names are also replaced inside config files and console logs, so the
original run names do not survive anywhere in the shared output.
"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path


def replace_in_file(path, mapping):
    text = path.read_text(encoding="utf-8")
    new = text
    for old, name in mapping.items():
        new = new.replace(old, name)
    if new != text:
        path.write_text(new, encoding="utf-8")


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    runs, swanlog, backup = Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    hide, mapping = set(spec["hide"]), spec["rename"]
    (backup / "runs").mkdir(parents=True, exist_ok=True)
    (backup / "swanlog").mkdir(parents=True, exist_ok=True)

    # sanitized dump
    for old in hide:
        if (runs / old).exists():
            shutil.move(str(runs / old), str(backup / "runs" / old))
    for old, name in mapping.items():
        if not (runs / old).exists():
            continue
        for f in ("run.json", "config.json", "console.log"):
            replace_in_file(runs / old / f, mapping)
        (runs / old).rename(runs / name)

    # local swanlog
    db = sqlite3.connect(swanlog / "runs.swanlab")
    db.execute("PRAGMA foreign_keys = ON")
    for exp_id, run_id, name in db.execute("SELECT id, run_id, name FROM experiment").fetchall():
        run_dir = swanlog / run_id
        if name in hide:
            db.execute("DELETE FROM experiment WHERE id = ?", (exp_id,))
            if run_dir.exists():
                shutil.move(str(run_dir), str(backup / "swanlog" / run_id))
        elif name in mapping:
            db.execute("UPDATE experiment SET name = ? WHERE id = ?", (mapping[name], exp_id))
            for f in [run_dir / "files" / "config.yaml", *(run_dir / "console").glob("*.log")]:
                replace_in_file(f, mapping)
    db.execute("UPDATE project SET sum = (SELECT count(*) FROM experiment)")
    db.commit()
    db.execute("VACUUM")
    db.close()

    # the raw record stream duplicates logs/ and still carries old names; the dashboard does not read it
    for f in swanlog.glob("run-*/run-*.swanlab"):
        shutil.move(str(f), str(backup / "swanlog" / f.name))


if __name__ == "__main__":
    main()

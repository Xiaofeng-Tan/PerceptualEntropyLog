"""Remove scalar metrics matching a regex from a project's dump and local swanlog.

Usage:
    python drop_keys.py <project_dir> <key_regex> [<console_field>]

    python drop_keys.py log/wan21_pec_final 'reward_temporal' reward_temporal

Matching keys are removed from runs/*/scalars*.json and from the dashboard
(tags, charts and their data files). If <console_field> is given,
`  <console_field>=<value>` fields are also stripped from console logs.
"""
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path


def main():
    project, key_re = Path(sys.argv[1]), re.compile(sys.argv[2])
    field = sys.argv[3] if len(sys.argv) > 3 else None
    field_re = re.compile(rf"\s+{re.escape(field)}=\S+") if field else None

    def strip_console(path):
        text = path.read_text(encoding="utf-8")
        new = field_re.sub("", text)
        if new != text:
            path.write_text(new, encoding="utf-8")

    for run in (project / "runs").iterdir():
        if not run.is_dir():
            continue
        for name in ("scalars.json", "scalars_aligned.json"):
            f = run / name
            if f.exists():
                data = json.loads(f.read_text())
                f.write_text(json.dumps({k: v for k, v in data.items() if not key_re.search(k)}))
        if field_re:
            strip_console(run / "console.log")

    swanlog = project / "swanlog"
    db = sqlite3.connect(swanlog / "runs.swanlab")
    db.execute("PRAGMA foreign_keys = ON")
    tags = [(i, n, f, r) for i, n, f, r in db.execute(
        "SELECT t.id, t.name, t.folder, e.run_id FROM tag t JOIN experiment e ON e.id = t.experiment_id")
        if key_re.search(n)]
    names = {n for _, n, _, _ in tags}
    for tag_id, _, folder, run_id in tags:
        shutil.rmtree(swanlog / run_id / "logs" / str(folder), ignore_errors=True)
        db.execute("DELETE FROM tag WHERE id = ?", (tag_id,))
    # charts are named after their key; drop those that no longer have a source
    for name in names:
        db.execute("DELETE FROM chart WHERE name = ? AND id NOT IN (SELECT chart_id FROM source)", (name,))
    db.commit()
    db.execute("VACUUM")
    db.close()
    if field_re:
        for f in swanlog.glob("run-*/console/*.log"):
            strip_console(f)
    print(f"{project}: removed {len(tags)} tags for keys {sorted(names)}")


if __name__ == "__main__":
    main()

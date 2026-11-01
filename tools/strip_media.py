"""Remove all images / videos from a project's sanitized dump and local swanlog.

Usage:
    python strip_media.py <project_dir>      # e.g. log/flux_pec_ddpo

Deletes runs/*/media/ and the media index files, and removes media tags,
their charts and stored files from swanlog/ so the dashboard shows scalars,
config and console logs only.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

MEDIA_TYPES = ("image", "audio", "video", "text", "object3d", "molecule", "echarts")


def main():
    project = Path(sys.argv[1])

    for run in (project / "runs").iterdir():
        if not run.is_dir():
            continue
        shutil.rmtree(run / "media", ignore_errors=True)
        for name in ("media.json", "media_aligned.json"):
            (run / name).unlink(missing_ok=True)
    (project / "runs" / ".gitignore").unlink(missing_ok=True)

    swanlog = project / "swanlog"
    db = sqlite3.connect(swanlog / "runs.swanlab")
    db.execute("PRAGMA foreign_keys = ON")
    marks = ",".join("?" * len(MEDIA_TYPES))
    rows = db.execute(
        f"SELECT t.id, t.folder, e.run_id FROM tag t JOIN experiment e ON e.id = t.experiment_id "
        f"WHERE lower(t.type) IN ({marks})", MEDIA_TYPES).fetchall()
    for _, folder, run_id in rows:
        shutil.rmtree(swanlog / run_id / "logs" / str(folder), ignore_errors=True)
    for run_dir in swanlog.glob("run-*"):
        shutil.rmtree(run_dir / "media", ignore_errors=True)
    db.execute(f"DELETE FROM chart WHERE lower(type) IN ({marks})", MEDIA_TYPES)
    db.execute(f"DELETE FROM tag WHERE lower(type) IN ({marks})", MEDIA_TYPES)
    # namespaces left without any chart (e.g. the media section) are dropped too
    db.execute("DELETE FROM namespace WHERE id NOT IN (SELECT namespace_id FROM display)")
    db.commit()
    db.execute("VACUUM")
    db.close()
    print(f"{project}: removed {len(rows)} media tags")


if __name__ == "__main__":
    main()

"""`python -m app.seed.cli [--reset]`: (re)seed the demo workspace. Also what `npm run seed` runs."""
from __future__ import annotations

import argparse
import sys

from .. import models
from ..db import SessionLocal, engine, init_db
from .run import get_demo_workspace, seed_demo


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the SIGNAL demo workspace")
    parser.add_argument("--reset", action="store_true", help="drop all data first")
    parser.add_argument("--posts", type=int, default=720)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    if args.reset:
        models.Base.metadata.drop_all(engine)
    init_db()
    with SessionLocal() as session:
        if not args.reset and get_demo_workspace(session) is not None:
            print("Demo workspace already exists; use --reset to rebuild.")
        ws = seed_demo(session, n_posts=args.posts, seed=args.seed)
        n = session.query(models.Post).filter(models.Post.workspace_id == ws.id).count()
        runs = session.query(models.ModelRun).filter(models.ModelRun.workspace_id == ws.id).count()
        exps = session.query(models.Experiment).filter(models.Experiment.workspace_id == ws.id).count()
        print(f"Seeded '{ws.name}': {n} posts, {runs} model runs, {exps} experiments.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

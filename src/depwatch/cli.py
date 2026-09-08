import argparse
import logging
import os
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config, run

log = logging.getLogger("depwatch")


def _services(path: str) -> run.Services:
    return run.build_services(config.load(Path(path), os.environ))


def _guarded(fn, s: run.Services):
    def job():
        try:
            fn(s, dry_run=False)
        except Exception:
            log.exception("%s run failed", fn.__name__)
    return job


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="depwatch")
    p.add_argument("--config", default="config.toml")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("digest", "advisory"):
        sp = sub.add_parser(name)
        sp.add_argument("--dry-run", action="store_true")
    sub.add_parser("serve")
    args = p.parse_args(argv)
    s = _services(args.config)
    if args.cmd == "digest":
        sys.stdout.write(run.digest(s, dry_run=args.dry_run))
        return 0
    if args.cmd == "advisory":
        sys.stdout.write(run.advisory(s, dry_run=args.dry_run))
        return 0
    sched = BlockingScheduler(timezone=s.config.timezone)
    sched.add_job(_guarded(run.digest, s), CronTrigger(day_of_week="mon", hour=7, minute=0), id="digest",
                  misfire_grace_time=3600)
    sched.add_job(_guarded(run.advisory, s), CronTrigger(day_of_week="tue-sun", hour=7, minute=0), id="advisory",
                  misfire_grace_time=3600)
    log.info("scheduler started, %d repos", len(s.config.allowlist))
    sched.start()
    return 0

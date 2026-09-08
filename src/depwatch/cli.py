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


def _guarded(fn, config_path: str):
    def job():
        s = _services(config_path)
        try:
            fn(s, dry_run=False)
        except Exception:
            log.exception("%s run failed", fn.__name__)
        finally:
            s.state.close()
    return job


def _build_scheduler(cfg: config.Config, config_path: str) -> BlockingScheduler:
    sched = BlockingScheduler(timezone=cfg.timezone)
    sched.add_job(_guarded(run.digest, config_path),
                  CronTrigger(day_of_week="mon", hour=7, minute=0, timezone=cfg.timezone),
                  id="digest", misfire_grace_time=3600)
    sched.add_job(_guarded(run.advisory, config_path),
                  CronTrigger(day_of_week="tue-sun", hour=7, minute=0, timezone=cfg.timezone),
                  id="advisory", misfire_grace_time=3600)
    return sched


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="depwatch")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("digest", "advisory"):
        sp = sub.add_parser(name)
        sp.add_argument("--config", default="config.toml")
        sp.add_argument("--dry-run", action="store_true")
    sp = sub.add_parser("serve")
    sp.add_argument("--config", default="config.toml")
    args = p.parse_args(argv)
    if args.cmd == "digest":
        sys.stdout.write(run.digest(_services(args.config), dry_run=args.dry_run))
        return 0
    if args.cmd == "advisory":
        sys.stdout.write(run.advisory(_services(args.config), dry_run=args.dry_run))
        return 0
    cfg = config.load(Path(args.config), os.environ)
    sched = _build_scheduler(cfg, args.config)
    log.info("scheduler started, %d repos", len(cfg.allowlist))
    sched.start()
    return 0

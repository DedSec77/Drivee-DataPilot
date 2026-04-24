from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from eval.harness import evaluate, load_golden_set, save_report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--path", type=Path, default=Path("eval/golden_set.yaml"))
    p.add_argument("--out", type=Path, default=Path("eval/results"))
    p.add_argument("--only", type=str, default="")
    p.add_argument("--skip-guards", action="store_true")
    args = p.parse_args()

    items = load_golden_set(args.path)
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        items = [it for it in items if it["id"] in wanted]
    if args.skip_guards:
        items = [it for it in items if not it.get("expected_guard")]

    logger.info(f"Evaluating {len(items)} items")
    report = evaluate(items)
    save_report(report, args.out)

    print()
    print(f"== Summary ({report.total} items) ==")
    print(f"  answered   : {report.answered}")
    print(f"  guard-pass : {report.guard_pass}")
    print(f"  EM mean    : {report.em_mean}")
    print(f"  CM mean    : {report.cm_mean}")
    print(f"  EX mean    : {report.ex_mean}")
    print(f"  VES mean   : {report.ves_mean}")
    print(f"  conf avg   : {report.avg_confidence}")
    print(f"  latency    : {report.avg_latency_ms} ms")
    print(f"Report saved -> {args.out}")


if __name__ == "__main__":
    main()

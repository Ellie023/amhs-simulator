"""
AMHS Simulator Entry Point

Usage:
  python main.py                   # 기본 실행 (seed=42, failover=12%)
  python main.py --seed 7          # 다른 시드
  python main.py --failover 0.2    # failover 확률 20%
  python main.py --verbose         # DEBUG 로그 출력
"""

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from src.simulator import AMHSSimulator


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "[%(levelname)s] %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)
    # 너무 많은 DEBUG 로그를 원하지 않으면 amhs.scheduler만 INFO로 제한
    if not verbose:
        logging.getLogger("amhs.scheduler").setLevel(logging.INFO)


def main():
    parser = argparse.ArgumentParser(description="FAB AMHS Simulator")
    parser.add_argument("--seed",     type=int,   default=42,   help="Random seed (default: 42)")
    parser.add_argument("--failover", type=float, default=0.12, help="OHT failover probability per tick (default: 0.12)")
    parser.add_argument("--maxticks", type=int,   default=300,  help="Maximum simulation ticks (default: 300)")
    parser.add_argument("--verbose",  action="store_true",       help="Enable DEBUG logging")
    args = parser.parse_args()

    setup_logging(args.verbose)

    print("\n" + "=" * 62)
    print("  FAB AMHS Simulator  (SK hynix AMHS Portfolio)")
    print("=" * 62)
    print(f"  seed={args.seed}  failover_prob={args.failover:.0%}  max_ticks={args.maxticks}")
    print("=" * 62 + "\n")

    sim = AMHSSimulator(
        seed=args.seed,
        failover_prob=args.failover,
        max_ticks=args.maxticks,
    )
    sim.run()


if __name__ == "__main__":
    main()

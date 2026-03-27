import argparse

import cacc
import cc
import racc


def parse_args():
    parser = argparse.ArgumentParser(
        description="Logic coverage reporter for Python programs."
    )
    parser.add_argument("target", help="Path to the target Python file to analyze")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--cc", action="store_true", help="Run Total Clause Coverage mode. (This mode is chosen if none is specified)")
    group.add_argument("--racc", action="store_true", help="Run Restricted Active Clause Coverage mode")
    group.add_argument("--cacc", action="store_true", help="Run Covered Active Clause Coverage mode")

    return parser.parse_args()


def main():
    args = parse_args()

    if args.racc:
        racc.run(args.target)
    elif args.cacc:
        cacc.run(args.target)
    else:
        cc.run(args.target)


if __name__ == "__main__":
    main()
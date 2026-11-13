import argparse
import csv
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dump-alerts-csv", metavar="PATH")
    args = p.parse_args()
    if args.dump_alerts_csv:
        with open(args.dump_alerts_csv, "w", newline="") as f:
            csv.writer(f).writerow(["device_id", "temperature"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

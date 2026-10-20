"""Load taxonomy/titles.csv into the jobTitles collection (key: code + title).

Usage: python mongoTitlesLoad.py [--dry-run] [--limit N] [--db D] [--collection C] [--include-manual]
Needs MONGO_URI unless --dry-run. See mongoload.py for the delete rules.
"""
import csv
import os

from mongoload import load, parse_args

HERE = os.path.dirname(os.path.abspath(__file__))


def read_docs(limit=None):
    with open(os.path.join(HERE, 'taxonomy', 'titles.csv'), newline='', encoding='utf-8') as f:
        for i, row in enumerate(csv.DictReader(f)):
            if limit and i >= limit:
                break
            yield row


if __name__ == '__main__':
    args = parse_args(__doc__)
    load(list(read_docs(args.limit)), 'jobTitles', ['code', 'title'], args)

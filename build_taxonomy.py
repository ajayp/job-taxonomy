"""Build the taxonomy source of truth from O*NET files.

Reads data/onet/* and any supplementary title CSVs (default data/supplementaryJobTitles.csv), writes
taxonomy/occupations.csv and taxonomy/titles.csv. The Mongo loaders read only those.

Usage: python build_taxonomy.py [--limit N] [--out DIR] [--supplement CSV ...]
  --supplement CSV  extra titles as code,title[,shortTitle]; repeatable, replaces the default file
  --limit N  keep only the first N occupations (and their titles), for smoke tests
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ONET_DIR = os.path.join(HERE, 'data', 'onet')

# White-collar rule (single place to change it): SOC major groups
# https://www.bls.gov/soc/2018/major_groups.htm and O*NET Job Zones 4/5
# https://www.onetonline.org/help/online/zones
WHITE_COLLAR_MAJOR_GROUPS = {'11', '13', '15', '17', '19', '21', '23', '25', '27', '29', '31', '33', '41', '43'}
WHITE_COLLAR_JOB_ZONES = {4, 5}

OCCUPATION_FIELDS = ['code', 'title', 'description', 'jobZone', 'whiteCollar',
                     'majorCode', 'majorGroup', 'minorCode', 'minorGroup',
                     'broadCode', 'broadOccupation', 'detailedCode']
DEFAULT_SUPPLEMENTS = [os.path.join(HERE, 'data', 'supplementaryJobTitles.csv')]
TITLE_FIELDS = ['code', 'title', 'shortTitle', 'source']


def read_tsv(name):
    with open(os.path.join(ONET_DIR, name), newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def load_soc_structure():
    """Return {detailed SOC code: hierarchy dict} from SOC_structure.csv (rows nest under the last seen parent)."""
    major = minor = broad = None
    lookup = {}
    with open(os.path.join(ONET_DIR, 'SOC_structure.csv'), newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            name = row['SOC or O*NET-SOC 2019 Title'].strip()
            if row['Major Group']:
                major, minor, broad = (row['Major Group'], name), None, None
            elif row['Minor Group']:
                minor, broad = (row['Minor Group'], name), None
            elif row['Broad Occupation']:
                broad = (row['Broad Occupation'], name)
            elif row['Detailed Occupation']:
                lookup[row['Detailed Occupation']] = {
                    'majorCode': major[0], 'majorGroup': major[1],
                    'minorCode': minor[0], 'minorGroup': minor[1],
                    'broadCode': broad[0], 'broadOccupation': broad[1],
                    'detailedCode': row['Detailed Occupation'],
                }
    return lookup


def build(limit=None, supplements=DEFAULT_SUPPLEMENTS):
    problems = []
    soc = load_soc_structure()
    zones = {r['O*NET-SOC Code']: int(r['Job Zone']) for r in read_tsv('Job Zones.txt')}

    occupations = []
    for r in read_tsv('Occupation Data.txt'):
        code = r['O*NET-SOC Code'].strip()
        h = soc.get(code[:7])
        if h is None:
            problems.append(f'occupation {code} not in SOC_structure.csv')
            h = {k: '' for k in OCCUPATION_FIELDS[5:]}
        zone = zones.get(code)
        occupations.append({
            'code': code, 'title': r['Title'].strip(), 'description': r['Description'].strip(),
            'jobZone': zone if zone is not None else '',
            'whiteCollar': code[:2] in WHITE_COLLAR_MAJOR_GROUPS and zone in WHITE_COLLAR_JOB_ZONES,
            **h,
        })
    if limit:
        occupations = occupations[:limit]
    codes = {o['code'] for o in occupations}

    titles, seen = [], set()

    def add(code, title, short, source):
        key = (code, title.lower())
        if not title or key in seen:
            return
        seen.add(key)
        titles.append({'code': code, 'title': title, 'shortTitle': short, 'source': source})

    for r in read_tsv('Job Titles.txt'):
        code = r['O*NET-SOC Code'].strip()
        if code in codes:
            short = r['Short Title'].strip()
            add(code, r['Job Title'].strip(), '' if short.lower() == 'n/a' else short, 'onet')

    # supplementary additions: code,title[,shortTitle]; must point at a known occupation
    for path in supplements:
        label = os.path.splitext(os.path.basename(path))[0]
        if label in ('manual', 'onet'):
            problems.append(f'supplement file name "{label}" is reserved; rename {path}')
            continue
        with open(path, newline='', encoding='utf-8-sig') as f:
            for row in csv.reader(f):
                row = [c.strip() for c in row]
                if len(row) < 2 or not row[0] or row[0] == 'O*NET-SOC Code' or not row[1]:
                    continue
                if not limit and row[0] not in codes:
                    problems.append(f'supplementary title "{row[1]}" ({label}) has unknown code {row[0]}')
                    continue
                if row[0] in codes:
                    add(row[0], row[1], row[2] if len(row) > 2 else '', label)
    return occupations, titles, problems


def write_csv(path, fields, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--limit', type=int)
    p.add_argument('--out', default=os.path.join(HERE, 'taxonomy'))
    p.add_argument('--supplement', action='append', default=None, metavar='CSV')
    args = p.parse_args()

    occupations, titles, problems = build(args.limit, args.supplement or DEFAULT_SUPPLEMENTS)
    os.makedirs(args.out, exist_ok=True)
    write_csv(os.path.join(args.out, 'occupations.csv'), OCCUPATION_FIELDS, occupations)
    write_csv(os.path.join(args.out, 'titles.csv'), TITLE_FIELDS, titles)

    wc = sum(1 for o in occupations if o['whiteCollar'])
    print(f'occupations: {len(occupations)} ({wc} white-collar), titles: {len(titles)}')
    for msg in problems:
        print('PROBLEM:', msg, file=sys.stderr)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()

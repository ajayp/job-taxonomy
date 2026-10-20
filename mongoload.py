"""Shared loader: replace the documents this pipeline owns, leave manual ones alone.

Owned documents are every document whose source is not RESERVED_SOURCE (written from
taxonomy/*.csv; source is 'onet' or the supplement file's name). Documents with source
"manual" are never deleted unless --include-manual.
Connection: MONGO_URI or MONGODB_URI; if the URI has no credentials or still has Atlas's
<username>/<password> placeholders, MONGODB_USERNAME / MONGODB_PASSWORD are filled in.
"""
import argparse
import json
import os
import sys
from urllib.parse import quote_plus

RESERVED_SOURCE = 'manual'
MAX_SHRINK = 0.2  # abort if the new load is more than 20% smaller than what it replaces


def resolve_uri(env=os.environ):
    uri = env.get('MONGO_URI') or env.get('MONGODB_URI')
    if not uri:
        return None
    user, pw = env.get('MONGODB_USERNAME'), env.get('MONGODB_PASSWORD')
    if user and pw:
        user, pw = quote_plus(user), quote_plus(pw)
        if '<username>' in uri or '<password>' in uri:
            uri = uri.replace('<username>', user).replace('<db_password>', pw).replace('<password>', pw)
        else:
            scheme, rest = uri.split('://', 1)
            if '@' not in rest.split('/')[0]:
                uri = f'{scheme}://{user}:{pw}@{rest}'
    return uri


def parse_args(description):
    p = argparse.ArgumentParser(description=description)
    p.add_argument('--db', default=os.getenv('MONGO_DB', 'jobTaxonomy'))
    p.add_argument('--collection', help='target collection (default: the loader\'s default)')
    p.add_argument('--dry-run', action='store_true', help='print documents and what would be deleted, change nothing')
    p.add_argument('--limit', type=int, help='load only the first N documents (smoke tests)')
    p.add_argument('--include-manual', action='store_true', help='also delete manual (non-owned) documents')
    p.add_argument('--force', action='store_true', help='skip the shrink guard')
    p.add_argument('--yes', action='store_true', help='skip the --include-manual confirmation')
    return p.parse_args()


def load(docs, default_collection, unique_keys, args, client=None):
    """docs: list of dicts, each with a non-reserved `source`. client is injectable for tests."""
    if not docs:
        sys.exit('nothing to load (empty taxonomy CSV?), aborting')
    bad = {d['source'] for d in docs} & {RESERVED_SOURCE}
    if bad:
        sys.exit(f'documents with reserved source {bad}, aborting')

    name = args.collection or default_collection
    target = {} if args.include_manual else {'source': {'$ne': RESERVED_SOURCE}}

    if args.dry_run and not (client or resolve_uri()):
        for d in docs[:20]:
            print(json.dumps(d)[:200])
        print(f'dry run: {len(docs)} documents for {args.db}.{name} (no MONGO_URI, nothing compared)')
        return

    if client is None:
        from pymongo import MongoClient
        uri = resolve_uri()
        if not uri:
            sys.exit('set MONGO_URI (or MONGODB_URI) in the environment')
        client = MongoClient(uri)
    coll = client[args.db][name]

    existing = coll.count_documents(target)
    owned = coll.count_documents({'source': {'$ne': RESERVED_SOURCE}})
    manual = coll.count_documents({'source': RESERVED_SOURCE}) if not args.include_manual else 0
    print(f'{args.db}.{name}: {existing} to delete, {len(docs)} to insert, {manual} manual kept')

    if owned and len(docs) < owned * (1 - MAX_SHRINK) and not args.force:
        sys.exit(f'new load is >{int(MAX_SHRINK * 100)}% smaller than existing ({len(docs)} vs {owned}); use --force if intended')
    if args.dry_run:
        return
    if args.include_manual and existing and not args.yes:
        if input(f'delete ALL {existing} documents including manual ones? type yes: ') != 'yes':
            sys.exit('cancelled')

    coll.create_index([(k, 1) for k in unique_keys], unique=True)
    coll.delete_many(target)
    for i in range(0, len(docs), 1000):
        coll.insert_many(docs[i:i + 1000], ordered=False)
    print(f'inserted {len(docs)}')

"""Tests the load/delete rules in mongoload.py against an in-memory Mongo (pip install mongomock)."""
import argparse
import unittest

import mongomock

from mongoload import load, resolve_uri


def args(**kw):
    base = dict(db='t', collection=None, dry_run=False, limit=None, include_manual=False, force=False, yes=True)
    return argparse.Namespace(**{**base, **kw})


def titles(n, source='onet', prefix='t'):
    return [{'code': '11-1011.00', 'title': f'{prefix}{i}', 'shortTitle': '', 'source': source} for i in range(n)]


class LoadRules(unittest.TestCase):
    def setUp(self):
        self.client = mongomock.MongoClient()
        self.coll = self.client['t']['jobTitles']

    def run_load(self, docs, **kw):
        load(docs, 'jobTitles', ['code', 'title'], args(**kw), client=self.client)

    def test_fresh_load(self):
        self.run_load(titles(10))
        self.assertEqual(self.coll.count_documents({}), 10)

    def test_reload_keeps_manual_and_drops_removed(self):
        self.run_load(titles(10))
        self.coll.insert_one({'code': '11-1011.00', 'title': 'Hand Added', 'source': 'manual'})
        self.run_load(titles(9))  # t9 removed upstream
        self.assertEqual(self.coll.count_documents({'source': 'manual'}), 1)
        self.assertEqual(self.coll.count_documents({'source': 'onet'}), 9)
        self.assertIsNone(self.coll.find_one({'title': 't9'}))

    def test_any_non_manual_source_is_owned(self):
        self.run_load(titles(5) + titles(5, source='extras', prefix='e'))
        self.run_load(titles(5) + titles(5, source='other', prefix='o'))
        self.assertEqual(self.coll.count_documents({'source': 'extras'}), 0)
        self.assertEqual(self.coll.count_documents({'source': 'other'}), 5)

    def test_shrink_guard_aborts_without_force(self):
        self.run_load(titles(10))
        with self.assertRaises(SystemExit):
            self.run_load(titles(5))
        self.assertEqual(self.coll.count_documents({}), 10)
        self.run_load(titles(5), force=True)
        self.assertEqual(self.coll.count_documents({}), 5)

    def test_include_manual_wipes_everything(self):
        self.run_load(titles(3))
        self.coll.insert_one({'code': 'x', 'title': 'm', 'source': 'manual'})
        self.run_load(titles(3), include_manual=True)
        self.assertEqual(self.coll.count_documents({'source': 'manual'}), 0)

    def test_dry_run_changes_nothing(self):
        self.run_load(titles(3))
        self.run_load(titles(4), dry_run=True)
        self.assertEqual(self.coll.count_documents({}), 3)

    def test_empty_and_reserved_source_rejected(self):
        with self.assertRaises(SystemExit):
            self.run_load([])
        with self.assertRaises(SystemExit):
            self.run_load(titles(2, source='manual'))


class ResolveUri(unittest.TestCase):
    def test_variants(self):
        creds = {'MONGODB_USERNAME': 'u', 'MONGODB_PASSWORD': 'p@ss'}
        self.assertIsNone(resolve_uri({}))
        self.assertEqual(resolve_uri({'MONGO_URI': 'mongodb+srv://x:y@h/'}), 'mongodb+srv://x:y@h/')
        self.assertEqual(resolve_uri({'MONGODB_URI': 'mongodb+srv://h/?a=b', **creds}), 'mongodb+srv://u:p%40ss@h/?a=b')
        self.assertEqual(resolve_uri({'MONGODB_URI': 'mongodb+srv://<username>:<password>@h/', **creds}), 'mongodb+srv://u:p%40ss@h/')
        self.assertEqual(resolve_uri({'MONGODB_URI': 'mongodb+srv://<username>:<db_password>@h/', **creds}), 'mongodb+srv://u:p%40ss@h/')


if __name__ == '__main__':
    unittest.main()

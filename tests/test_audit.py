import unittest
from database_claim_audit.phrases import DATABASE, NODATABASE

EXPECTED_DATABASE = ('stores data in a database', 'store data in a database', 'uses a database', 'use a database', 'database storage', 'stores records in a database', 'store records in a database', 'queries the database', 'query the database', 'saves data to a database', 'save data to a database', 'persists data to a database', 'persist data to a database', 'writes data to a database', 'write data to a database', 'reads data from a database', 'read data from a database', 'backed by a database', 'database backed', 'database persistence', 'stores data in sqlite', 'store data in sqlite', 'uses sqlite', 'use sqlite', 'stores data in postgresql', 'store data in postgresql', 'uses postgresql', 'use postgresql', 'stores data in postgres', 'store data in postgres', 'uses postgres', 'use postgres', 'stores data in mysql', 'store data in mysql', 'uses mysql', 'use mysql', 'stores data in mongodb', 'store data in mongodb', 'uses mongodb', 'use mongodb', 'sql database', 'relational database', 'nosql database', 'document database', 'sqlite database', 'postgresql database', 'postgres database', 'mysql database', 'mongodb database', 'stores data in a sql database')
EXPECTED_NODATABASE = ('does not store data in a database', 'never stores data in a database', 'does not use a database', 'never uses a database', 'does not query the database', 'never queries the database', 'does not save data to a database', 'never saves data to a database', 'does not persist data to a database', 'never persists data to a database', 'does not write data to a database', 'never writes data to a database', 'does not read data from a database', 'never reads data from a database', 'does not use sqlite', 'never uses sqlite', 'does not use postgresql', 'never uses postgresql', 'does not use mysql', 'never uses mysql', 'does not use mongodb', 'never uses mongodb', 'no database storage', 'no database persistence')

class PhraseOracle(unittest.TestCase):
    def test_phrases(self):
        self.assertEqual(DATABASE, EXPECTED_DATABASE)
        self.assertEqual(NODATABASE, EXPECTED_NODATABASE)

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from database_claim_audit.audit import audit, claims, evidence, GENERIC

class EvidenceTests(unittest.TestCase):
    def test_routes(self):
        samples = [
            'import sqlite3\nsqlite3.connect(":memory:")\nc.execute("x")',
            'import sqlite3 as s\ns.connect("x")\nc.executemany("x", [])',
            'from sqlite3 import connect as c\nc("x")\nx.executescript("x")',
            'from sqlalchemy import create_engine\ncreate_engine("x")\nc.execute("x")',
            'from sqlalchemy.orm import Session\nSession()\ns.add(x)\ns.commit()',
            'import sqlalchemy.orm as orm\norm.Session()\ns.query(x)',
            'from sqlalchemy.orm import sessionmaker\nsessionmaker()\ns.add(x)\ns.commit()',
            'from sqlalchemy.orm import Session\nSession()\ns.execute(x)',
            'import psycopg2\npsycopg2.connect()\nc.execute(x)',
            'import pymysql\npymysql.connect()\nc.execute(x)',
            'import MySQLdb\nMySQLdb.connect()\nc.executemany(x)',
            *['from pymongo import MongoClient\nMongoClient()\nc.'+op+'()' for op in ('insert_one','insert_many','replace_one','update_one','update_many','delete_one','delete_many','find_one','find','find_one_and_update','find_one_and_replace','find_one_and_delete')],
            'from pandas import read_sql\nread_sql(x, y)', 'x.to_sql(x)',
            *['User.objects.'+op+'()' for op in ('create','get','get_or_create','update_or_create','filter','exclude','all','update','delete','first','last','count','exists')],
            *['x.'+op+'()' for op in GENERIC], 'from thing import store_in_database as store\nstore()',
        ]
        for source in samples:
            with self.subTest(source=source): self.assertTrue(evidence(source))

    def test_non_evidence(self):
        samples = ['import sqlite3\nsqlite3.connect("x")', 'import psycopg2\npsycopg2.connect()', 'import pymysql\npymysql.connect()', 'from pymongo import MongoClient\nMongoClient()', 'from sqlalchemy import create_engine\ncreate_engine("x")', 'from sqlalchemy.orm import Session, sessionmaker\nSession()\nsessionmaker()\ns.add(x)', 'x.execute(x)', '"SELECT * FROM x"', 'class X(models.Model): pass', 'import pandas', 'df.to_csv("x")', 'r.set(x,y)', 'json.dump(x,y)', 'csv.writer(x)', 'x = {}', 'subprocess.run(["sqlite3"])', '"database"', 'mindee.parse(x)', 'azure.begin_analyze_document(x)', 'veryfi.Client()', 'documentai.process_document(x)', 'textract.analyze_document(x)', 'eden.call(x)', 'llamaparse.parse(x)', 'nanonets.ocr(x)', 'docsumo.upload(x)', 'query_database()', 'from x import query_database\ndef query_database(): pass\nquery_database()', 'import sqlite3\ndef connect(): pass\nsqlite3.connect("x")\nc.execute(x)', 'from sqlite3 import connect\nwith x as connect: pass\nconnect()\nc.execute(x)']
        for source in samples:
            with self.subTest(source=source): self.assertFalse(evidence(source))

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
    def write(self, name, content):
        p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)
    def test_findings_and_no_source(self):
        self.write('README.md', 'stores data in a database')
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')
        self.write('tests/test_x.py', 'import sqlite3\nsqlite3.connect("x")\nc.execute("x")')
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'MEDIUM')
        self.write('app.py', 'import sqlite3\nsqlite3.connect("x")\nc.execute("x")')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.write('README.md', 'does not store data in a database')
        self.assertEqual(audit(self.root)['findings'][0]['id'], 'documented-no-database-claim-false')
        (self.root / 'app.py').unlink()
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
    def test_split_and_exclusions(self):
        self.write('README.md', 'uses a database')
        self.write('a.py', 'import sqlite3\nsqlite3.connect("x")')
        self.write('b.py', 'c.execute("x")')
        self.write('examples/x.py', 'x.to_sql()')
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')
        (self.root / 'link.py').symlink_to(self.root / 'examples/x.py')
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')
    def test_claims(self):
        self.assertEqual(claims('```\nuses a database\n```'), (False, False))
        self.assertEqual(claims('`uses a database`'), (True, False))
        self.assertEqual(claims('does not use a database'), (False, True))
        self.assertEqual(claims('USES-A-DATABASE'), (True, False))
        self.assertEqual(claims('nothing here'), (False, False))
    def test_cli(self):
        self.write('README.md', 'uses a database')
        cmd = [sys.executable, '-m', 'database_claim_audit', 'audit', str(self.root)]
        p = subprocess.run(cmd + ['--json'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2); self.assertEqual(json.loads(p.stdout)['findings'][0]['id'], 'documented-database-claim-false')
        self.write('tests/test_x.py', 'x.to_sql()')
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run(cmd + ['--fail-on', 'medium'], capture_output=True).returncode, 2)
        self.assertEqual(subprocess.run([sys.executable, '-m', 'database_claim_audit', '--version'], capture_output=True, text=True).stdout.strip(), '0.1.0')

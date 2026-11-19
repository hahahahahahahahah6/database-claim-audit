"""Static documentation and source inspection."""
import ast
import os
import re
from pathlib import Path
from .phrases import DATABASE, NODATABASE

GENERIC = frozenset('store_in_database save_to_database query_database insert_record insert_into_database fetch_records fetch_from_database execute_query run_query database_insert write_to_db read_from_db persist_to_database load_from_database upsert_record delete_from_database create_table drop_table update_record select_from_database insert_row query_db save_record get_from_database'.split())
MONGO = frozenset('insert_one insert_many replace_one update_one update_many delete_one delete_many find_one find find_one_and_update find_one_and_replace find_one_and_delete'.split())
DJANGO = frozenset('create get get_or_create update_or_create filter exclude all update delete first last count exists'.split())

def normalize(text):
    text = text.lower().replace('’', "'")
    text = re.sub(r"n['’]t\b", ' not', text)
    return ' '.join(text.replace('-', ' ').split())

def patterns(phrases):
    return [(p, re.compile(r'(?<!\w)' + re.escape(p) + r'(?!\w)')) for p in sorted(phrases, key=lambda x: (-len(x), x))]

YES = patterns(DATABASE)
NO = patterns(NODATABASE)

def claims(text):
    lines = []
    fence = None
    for line in text.splitlines():
        m = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not m.group(2).strip():
                fence = None
            continue
        if m:
            fence = m.group(1)
            continue
        lines.append(line)
    yes = no = False
    for para in re.split(r'\n\s*\n', '\n'.join(lines)):
        value = normalize(para)
        for _, pattern in NO:
            value, count = pattern.subn(' ', value)
            no |= bool(count)
        yes |= any(pattern.search(value) for _, pattern in YES)
    return yes, no

def evidence(text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return False
    nodes = list(ast.walk(tree))
    shadows = {n.name for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    imports = {}
    for n in nodes:
        if isinstance(n, ast.Import):
            for a in n.names:
                imports[a.asname or a.name.split('.')[0]] = a.name if a.asname else a.name.split('.')[0]
        elif isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                if a.name != '*':
                    imports[a.asname or a.name] = n.module + '.' + a.name
    bound = set()
    def names(target):
        if isinstance(target, ast.Name):
            bound.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts: names(item)
    for n in nodes:
        if isinstance(n, ast.Assign):
            for t in n.targets: names(t)
        elif isinstance(n, ast.AnnAssign): names(n.target)
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            for item in n.items:
                if item.optional_vars: names(item.optional_vars)
    for name in shadows | bound:
        imports.pop(name, None)
    calls = [n.func for n in nodes if isinstance(n, ast.Call)]
    attrs = {f.attr for f in calls if isinstance(f, ast.Attribute)}
    def route(f, target):
        if isinstance(f, ast.Name):
            return f.id not in shadows and imports.get(f.id) == target
        if isinstance(f, ast.Attribute) and f.attr == target.rsplit('.', 1)[-1] and f.attr not in shadows:
            base = f.value
            chain = []
            while isinstance(base, ast.Attribute):
                chain.append(base.attr)
                base = base.value
            if isinstance(base, ast.Name) and base.id not in shadows and base.id in imports:
                path = imports[base.id] + ('.' + '.'.join(reversed(chain)) if chain else '')
                return path == target.rsplit('.', 1)[0] or path.startswith(target.rsplit('.', 1)[0] + '.')
        return False
    def has(target): return any(route(f, target) for f in calls)
    if has('sqlite3.connect') and attrs & {'execute', 'executemany', 'executescript'}: return True
    if has('sqlalchemy.create_engine') and 'execute' in attrs: return True
    if any(has('sqlalchemy.orm.' + x) for x in ('Session', 'sessionmaker')) and attrs & {'commit', 'query', 'execute'}: return True
    if any(has(x + '.connect') for x in ('psycopg2', 'pymysql', 'MySQLdb')) and attrs & {'execute', 'executemany'}: return True
    if has('pymongo.MongoClient') and attrs & MONGO: return True
    if has('pandas.read_sql') or 'to_sql' in attrs: return True
    for f in calls:
        if isinstance(f, ast.Attribute):
            if f.attr in DJANGO and isinstance(f.value, ast.Attribute) and f.value.attr == 'objects': return True
            if f.attr in GENERIC and f.attr not in shadows: return True
        elif isinstance(f, ast.Name) and f.id not in shadows and imports.get(f.id, '').rsplit('.', 1)[-1] in GENERIC: return True
    return False

def audit(root='.', ignore=()):
    root = Path(root)
    if root.is_symlink() or not root.is_dir(): raise OSError('repository is not a directory: ' + str(root))
    yes = no = prod = test = False
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=lambda e: (_ for _ in ()).throw(e)):
        base = Path(directory)
        dirs[:] = [d for d in dirs if not (base / d).is_symlink() and not any((base / d).relative_to(root).as_posix().startswith(p) for p in ignore)]
        for filename in files:
            path = base / filename
            rel = path.relative_to(root)
            if path.is_symlink() or any(rel.as_posix().startswith(p) for p in ignore): continue
            parts = rel.parts
            if (len(parts) == 1 and filename == 'README.md') or ('docs' in parts[:-1] and filename.endswith('.md')):
                y, n = claims(path.read_text(encoding='utf-8')); yes |= y; no |= n
            if filename.endswith('.py') and not set(parts[:-1]) & {'fixtures', 'docs', 'examples'}:
                found = evidence(path.read_text(encoding='utf-8'))
                is_test = 'tests' in parts[:-1] or filename.startswith('test_') or filename.endswith('_test.py')
                if is_test: test |= found
                else: prod |= found
    findings = []
    if yes and not prod:
        findings.append({'id': 'documented-database-claim-false', 'severity': 'MEDIUM' if test else 'HIGH', 'message': 'Documented capability has evidence only in tests.' if test else 'Documented capability has no production evidence.'})
    if no and prod:
        findings.append({'id': 'documented-no-database-claim-false', 'severity': 'HIGH', 'message': 'Documented denial conflicts with production evidence.'})
    return {'verdict': 'FAIL' if findings else 'PASS', 'findings': findings}

# Documentation claim auditor

This offline static checker compares exact documentation phrases with Python source patterns. It examines the root README and Markdown under docs, excluding fenced blocks; inline code counts. It scans source without executing it. Install and run:

```sh
pip install dist/database_claim_audit-0.1.0-py3-none-any.whl
database-claim-audit audit . --json
database-claim-audit audit . --fail-on medium --ignore vendor/
python3 -m database_claim_audit --version
```

Findings are reported as follows:

```text
documented-database-claim-false: HIGH, or MEDIUM when evidence exists only in tests
documented-no-database-claim-false: HIGH
```

Exit status is 0 for a passing threshold, 2 for findings at or above the threshold, and 1 for usage or I/O errors. The default threshold is high. Ignore prefixes are relative paths and can be repeated. Test files are considered separately; fixtures, docs, examples, and symlinks are excluded from source evidence.

Detection is limited to exact phrases and static patterns. Dead code counts, and unsupported alias chains can be missed. A connection and its operation must occur in the same module. A connection alone, an execution call alone, a SQL literal, or a model declaration alone is insufficient. A session addition requires a commit in the same module. A client construction alone is insufficient. File exports, file storage, in-memory collections, caches, and subprocess commands are excluded. A SQLite-backed cache with a connection and execution pair can satisfy this checker and a cache checker alike.

Document extraction calls from Mindee, Azure, Veryfi, Google Document AI, Eden AI, Textract, LlamaParse, Nanonets, Docsumo, ABBYY, Rossum, Klippa, Parseur, and Extend are excluded. Unrelated feature claims are outside the phrase list. A phrase can describe an external service, a reference file, or a subprocess implementation that this static check cannot establish; review findings in context. Denial handling is limited to the listed exact phrases.

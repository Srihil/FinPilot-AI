# Pure unit tests — no database, no server.
# This empty conftest.py prevents the parent conftest.py from running
# its autouse session fixture that tries to connect to PostgreSQL.

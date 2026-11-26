import re
import sqlite3
import threading
from urllib.parse import urlparse


class IntegrityError(Exception):
	pass


class HybridRow(dict):
	def __init__(self, names, values):
		super().__init__(zip(names, values))
		self._values = values

	def __getitem__(self, key):
		if isinstance(key, int):
			return self._values[key]
		return super().__getitem__(key)


class DatabaseCursor:
	def __init__(self, cursor, remote):
		self.cursor = cursor
		self.remote = remote
		self.lastrowid = None

	def _row(self, row):
		if row is None or not self.remote:
			return row
		names = [column.name for column in self.cursor.description]
		return HybridRow(names, row)

	def fetchone(self):
		return self._row(self.cursor.fetchone())

	def fetchall(self):
		return [self._row(row) for row in self.cursor.fetchall()]

	def __getattr__(self, name):
		return getattr(self.cursor, name)


class DatabaseConnection:
	def __init__(self, location, timeout=10, check_same_thread=True):
		self.location = location
		self.remote = is_remote(location)
		self._lock = threading.RLock()
		self._raw = None
		if self.remote:
			try:
				import psycopg
			except ImportError as exc:
				raise RuntimeError("Per DB_LOCATION remoto installa la dipendenza psycopg[binary].") from exc
			self._raw = psycopg.connect(location, connect_timeout=timeout)
			self._integrity_error = psycopg.IntegrityError
		else:
			self._raw = sqlite3.connect(location, timeout=timeout, check_same_thread=check_same_thread)
			self._raw.row_factory = sqlite3.Row
			self._raw.execute("PRAGMA foreign_keys = ON")
			self._integrity_error = sqlite3.IntegrityError

	def execute(self, sql, parameters=()):
		try:
			with self._lock:
				if not self.remote:
					return self._raw.execute(sql, parameters)
				statement = self._translate(sql)
				cursor = self._raw.cursor()
				cursor.execute(statement, parameters)
				result = DatabaseCursor(cursor, remote=True)
				if cursor.description and cursor.description[0].name == "id" and statement.lstrip().upper().startswith("INSERT"):
					result.lastrowid = cursor.fetchone()[0]
				return result
		except self._integrity_error as exc:
			raise IntegrityError(str(exc)) from exc

	def executemany(self, sql, parameters):
		try:
			with self._lock:
				if not self.remote:
					return self._raw.executemany(sql, parameters)
				cursor = self._raw.cursor()
				cursor.executemany(self._translate(sql), parameters)
				return DatabaseCursor(cursor, remote=True)
		except self._integrity_error as exc:
			raise IntegrityError(str(exc)) from exc

	def executescript(self, script):
		if not self.remote:
			return self._raw.executescript(script)
		result = None
		for statement in script.split(";"):
			if statement.strip():
				result = self.execute(statement)
		return result

	def table_columns(self, table_name):
		if not self.remote:
			return [row["name"] for row in self.execute(f"PRAGMA table_info({table_name})").fetchall()]
		rows = self.execute(
			"SELECT column_name AS name FROM information_schema.columns "
			"WHERE table_schema = current_schema() AND table_name = ? ORDER BY ordinal_position",
			(table_name,),
		).fetchall()
		return [row["name"] for row in rows]

	def _translate(self, sql):
		statement = sql.strip()
		if statement.upper().startswith("PRAGMA "):
			return "SELECT 1"
		statement = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "BIGSERIAL PRIMARY KEY", statement, flags=re.IGNORECASE)
		statement = re.sub(r"\bINTEGER\b", "BIGINT", statement, flags=re.IGNORECASE)
		statement = re.sub(r"\bBLOB\b", "BYTEA", statement, flags=re.IGNORECASE)
		statement = re.sub(r"\bDATETIME\b", "TIMESTAMP", statement, flags=re.IGNORECASE)
		statement = re.sub(
			r"\b([A-Za-z_][\w.]*)\s*=\s*(\?|%s)\s+COLLATE\s+NOCASE\b",
			r"LOWER(\1) = LOWER(\2)",
			statement,
			flags=re.IGNORECASE,
		)
		statement = re.sub(r"\b(ORDER\s+BY\s+)([A-Za-z_][\w.]*)\s+COLLATE\s+NOCASE\b", r"\1LOWER(\2)", statement, flags=re.IGNORECASE)
		statement = re.sub(r"\s+COLLATE\s+NOCASE\b", "", statement, flags=re.IGNORECASE)
		statement = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", statement, flags=re.IGNORECASE)
		if re.search(r"\bINSERT\s+INTO\b", statement, flags=re.IGNORECASE) and "OR IGNORE" in sql.upper():
			statement += " ON CONFLICT DO NOTHING"
		if statement.upper().startswith("INSERT INTO") and re.search(r"\bINTO\s+(personaggi|web_users)\b", statement, flags=re.IGNORECASE) and "RETURNING" not in statement.upper():
			statement += " RETURNING id"
		statement = statement.replace("?", "%s")
		return statement

	def commit(self):
		with self._lock:
			self._raw.commit()

	def rollback(self):
		with self._lock:
			self._raw.rollback()

	def close(self):
		with self._lock:
			self._raw.close()

	def __enter__(self):
		self._lock.acquire()
		try:
			if not self.remote:
				self._raw.__enter__()
			return self
		except Exception:
			self._lock.release()
			raise

	def __exit__(self, exc_type, exc_value, traceback):
		try:
			if not self.remote:
				return self._raw.__exit__(exc_type, exc_value, traceback)
			if exc_type is None:
				self._raw.commit()
			else:
				self._raw.rollback()
			return False
		finally:
			self._lock.release()


def is_remote(location):
	if not isinstance(location, str):
		return False
	scheme = urlparse(location).scheme.lower()
	return scheme in {"postgres", "postgresql"}


def connect(location, timeout=10, check_same_thread=True):
	return DatabaseConnection(location, timeout=timeout, check_same_thread=check_same_thread)

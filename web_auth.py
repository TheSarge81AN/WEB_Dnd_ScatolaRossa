import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager


SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
ADMIN_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.&-]{1,64}$")


class WebAuthStore:
	def __init__(self, db_path, users_path, admin_username="", admin_password=""):
		self.db_path = db_path
		self.users_path = users_path
		self.admin_username = ""
		self.admin_password = ""
		self.file_lock = threading.Lock()
		if not os.path.exists(self.users_path):
			self._write_users([])
		with self._connect() as conn:
			conn.executescript("""
				CREATE TABLE IF NOT EXISTS web_users (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					username TEXT NOT NULL COLLATE NOCASE UNIQUE,
					password_salt BLOB NOT NULL,
					password_hash BLOB NOT NULL,
					created_at INTEGER NOT NULL
				);
				CREATE TABLE IF NOT EXISTS web_sessions (
					token_hash TEXT PRIMARY KEY,
					user_id INTEGER NOT NULL,
					expires_at INTEGER NOT NULL,
					FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE CASCADE
				);
				CREATE TABLE IF NOT EXISTS web_character_owners (
					character_name TEXT PRIMARY KEY COLLATE NOCASE,
					user_id INTEGER NOT NULL,
					FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE CASCADE
				);
				CREATE TABLE IF NOT EXISTS web_adventure_members (
					adventure_id TEXT NOT NULL,
					user_id INTEGER NOT NULL,
					PRIMARY KEY (adventure_id, user_id),
					FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE CASCADE
				);
				CREATE TABLE IF NOT EXISTS web_adventure_owners (
					adventure_id TEXT PRIMARY KEY,
					user_id INTEGER NOT NULL,
					FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE CASCADE
				);
			""")
		if admin_username or admin_password:
			self.configure_admin(admin_username, admin_password)

	@contextmanager
	def _connect(self):
		conn = sqlite3.connect(self.db_path, timeout=10)
		conn.row_factory = sqlite3.Row
		conn.execute("PRAGMA foreign_keys = ON")
		try:
			yield conn
			conn.commit()
		except Exception:
			conn.rollback()
			raise
		finally:
			conn.close()

	def _user_view(self, row):
		return {
			"id": row["id"],
			"username": row["username"],
			"is_admin": self._is_admin_name(row["username"]),
		}

	@staticmethod
	def _password_hash(password, salt):
		return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)

	def _is_admin_name(self, username):
		return bool(self.admin_username) and username.casefold() == self.admin_username.casefold()

	def _read_users_locked(self):
		try:
			with open(self.users_path, "r", encoding="utf-8") as file:
				data = json.load(file)
		except json.JSONDecodeError as exc:
			raise ValueError(f"Il file utenti_web.json non è JSON valido (riga {exc.lineno}).") from exc
		users = data.get("users") if isinstance(data, dict) else None
		if not isinstance(users, list) or any(
			not isinstance(user, dict)
			or not isinstance(user.get("username"), str)
			or not USERNAME_PATTERN.fullmatch(user["username"])
			for user in users
		):
			raise ValueError("Il file utenti_web.json deve contenere account con nomi utente validi nell'array 'users'.")
		return users

	def _write_users_locked(self, users):
		temp_path = self.users_path + ".tmp"
		try:
			with open(temp_path, "w", encoding="utf-8") as file:
				json.dump({"users": users}, file, ensure_ascii=False, indent=2)
				file.write("\n")
			os.replace(temp_path, self.users_path)
		finally:
			if os.path.exists(temp_path):
				os.remove(temp_path)

	def _write_users(self, users):
		with self.file_lock:
			self._write_users_locked(users)

	def _sync_user(self, username, salt, password_hash):
		with self._connect() as conn:
			row = conn.execute("SELECT id FROM web_users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
			if row:
				conn.execute(
					"UPDATE web_users SET password_salt = ?, password_hash = ? WHERE id = ?",
					(salt, password_hash, row["id"])
				)
				user_id = row["id"]
			else:
				cursor = conn.execute(
					"INSERT INTO web_users (username, password_salt, password_hash, created_at) VALUES (?, ?, ?, ?)",
					(username, salt, password_hash, int(time.time()))
				)
				user_id = cursor.lastrowid
			row = conn.execute("SELECT id, username FROM web_users WHERE id = ?", (user_id,)).fetchone()
		return self._user_view(row)

	def configure_admin(self, username, password):
		username = str(username or "").strip()
		password = str(password or "")
		if not ADMIN_USERNAME_PATTERN.fullmatch(username) or len(password) < 10 or len(password) > 1024:
			raise ValueError("WEB_USERNAME deve contenere 1-64 lettere, numeri, punto, trattino, underscore o '&'; DnD_USER_PASSWORD deve contenere almeno 10 caratteri.")
		with self.file_lock:
			users = self._read_users_locked()
			if any(str(user["username"]).casefold() == username.casefold() for user in users):
				raise ValueError("Rimuovi l'account amministratore da utenti_web.json: è gestito dalle variabili d'ambiente.")
		self.admin_username = username
		self.admin_password = password
		with self._connect() as conn:
			row = conn.execute(
				"SELECT id, password_salt, password_hash FROM web_users WHERE username = ? COLLATE NOCASE",
				(username,)
			).fetchone()
			if row and hmac.compare_digest(self._password_hash(password, row["password_salt"]), row["password_hash"]):
				return
			salt = secrets.token_bytes(16)
			password_hash = self._password_hash(password, salt)
			if row:
				conn.execute(
					"UPDATE web_users SET password_salt = ?, password_hash = ? WHERE id = ?",
					(salt, password_hash, row["id"])
				)
				conn.execute("DELETE FROM web_sessions WHERE user_id = ?", (row["id"],))
			else:
				conn.execute(
					"INSERT INTO web_users (username, password_salt, password_hash, created_at) VALUES (?, ?, ?, ?)",
					(username, salt, password_hash, int(time.time()))
				)

	def _validate_account(self, username, password):
		username = str(username or "").strip()
		password = str(password or "")
		if not USERNAME_PATTERN.fullmatch(username):
			raise ValueError("Il nome utente deve contenere 3-32 caratteri: lettere, numeri, punto, trattino o underscore.")
		if len(password) < 10 or len(password) > 1024:
			raise ValueError("La password deve contenere 10-1024 caratteri.")
		if self._is_admin_name(username):
			raise ValueError("Il nome dell'amministratore è riservato.")
		return username, password

	def add_user(self, username, password):
		username, password = self._validate_account(username, password)
		with self.file_lock:
			users = self._read_users_locked()
			if any(str(user.get("username", "")).casefold() == username.casefold() for user in users):
				raise ValueError("Nome utente già utilizzato.")
			salt = secrets.token_bytes(16)
			users.append({"username": username, "salt": salt.hex(), "password_hash": self._password_hash(password, salt).hex()})
			self._write_users_locked(users)
		return self._sync_user(username, salt, bytes.fromhex(users[-1]["password_hash"]))

	def update_password(self, username, password):
		username, password = self._validate_account(username, password)
		with self.file_lock:
			users = self._read_users_locked()
			account = next((user for user in users if str(user.get("username", "")).casefold() == username.casefold()), None)
			if not account:
				raise ValueError("Utente non trovato.")
			salt = secrets.token_bytes(16)
			password_hash = self._password_hash(password, salt)
			account["salt"] = salt.hex()
			account["password_hash"] = password_hash.hex()
			self._write_users_locked(users)
		with self._connect() as conn:
			conn.execute(
				"UPDATE web_users SET password_salt = ?, password_hash = ? WHERE username = ? COLLATE NOCASE",
				(salt, password_hash, username)
			)
			conn.execute("DELETE FROM web_sessions WHERE user_id = (SELECT id FROM web_users WHERE username = ? COLLATE NOCASE)", (username,))
		return True

	def delete_user(self, username):
		username = str(username or "").strip()
		if self._is_admin_name(username):
			raise ValueError("L'account amministratore non può essere eliminato da questa pagina.")
		with self.file_lock:
			users = self._read_users_locked()
			remaining = [user for user in users if str(user.get("username", "")).casefold() != username.casefold()]
			if len(remaining) == len(users):
				raise ValueError("Utente non trovato.")
			self._write_users_locked(remaining)
		with self._connect() as conn:
			conn.execute("DELETE FROM web_users WHERE username = ? COLLATE NOCASE", (username,))
		return True

	def list_users(self):
		with self.file_lock:
			users = self._read_users_locked()
		return sorted((str(user["username"]) for user in users), key=str.casefold)

	def authenticate(self, username, password):
		username = str(username or "").strip()
		password = str(password or "")
		if len(password) > 1024:
			return None
		if self._is_admin_name(username):
			if not hmac.compare_digest(password.encode("utf-8"), self.admin_password.encode("utf-8")):
				return None
			with self._connect() as conn:
				row = conn.execute("SELECT id, username FROM web_users WHERE username = ? COLLATE NOCASE", (self.admin_username,)).fetchone()
			return self._user_view(row) if row else None
		with self.file_lock:
			users = self._read_users_locked()
			account = next((user for user in users if str(user.get("username", "")).casefold() == username.casefold()), None)
		if not account:
			self._password_hash(password, b"dnd-web-dummy-salt")
			return None
		try:
			salt = bytes.fromhex(account["salt"])
			stored_hash = bytes.fromhex(account["password_hash"])
		except (KeyError, TypeError, ValueError) as exc:
			raise ValueError(f"Credenziali non valide nel record JSON per {username}.") from exc
		candidate = self._password_hash(password, salt)
		if not hmac.compare_digest(candidate, stored_hash):
			return None
		return self._sync_user(account["username"], salt, stored_hash)

	def create_session(self, user_id):
		token = secrets.token_urlsafe(32)
		token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
		expires_at = int(time.time()) + SESSION_TTL_SECONDS
		with self._connect() as conn:
			conn.execute(
				"INSERT INTO web_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
				(token_hash, user_id, expires_at)
			)
		return token

	def get_user(self, token):
		if not token:
			return None
		token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
		now = int(time.time())
		with self._connect() as conn:
			row = conn.execute("""
				SELECT u.id, u.username, u.password_hash, s.expires_at
				FROM web_sessions s JOIN web_users u ON u.id = s.user_id
				WHERE s.token_hash = ?
			""", (token_hash,)).fetchone()
			if not row:
				return None
			if row["expires_at"] <= now:
				conn.execute("DELETE FROM web_sessions WHERE token_hash = ?", (token_hash,))
				return None
			if not self._is_admin_name(row["username"]):
				with self.file_lock:
					users = self._read_users_locked()
					account = next((user for user in users if str(user.get("username", "")).casefold() == row["username"].casefold()), None)
				valid = False
				if account:
					try:
						valid = hmac.compare_digest(bytes.fromhex(account["password_hash"]), row["password_hash"])
					except (KeyError, TypeError, ValueError):
						valid = False
				if not valid:
					conn.execute("DELETE FROM web_sessions WHERE token_hash = ?", (token_hash,))
					return None
		return self._user_view(row)

	def delete_session(self, token):
		if not token:
			return
		token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
		with self._connect() as conn:
			conn.execute("DELETE FROM web_sessions WHERE token_hash = ?", (token_hash,))

	def owns_character(self, user_id, character_name):
		with self._connect() as conn:
			row = conn.execute(
				"SELECT 1 FROM web_character_owners WHERE user_id = ? AND character_name = ? COLLATE NOCASE",
				(user_id, character_name)
			).fetchone()
		return row is not None

	def claim_character(self, user_id, character_name):
		try:
			with self._connect() as conn:
				conn.execute(
					"INSERT INTO web_character_owners (character_name, user_id) VALUES (?, ?)",
					(character_name, user_id)
				)
		except sqlite3.IntegrityError as exc:
			raise ValueError("Il personaggio è già associato a un account.") from exc

	def character_names(self, user_id):
		with self._connect() as conn:
			rows = conn.execute(
				"SELECT character_name FROM web_character_owners WHERE user_id = ? ORDER BY character_name COLLATE NOCASE",
				(user_id,)
			).fetchall()
		return {row["character_name"] for row in rows}

	def add_member(self, user_id, adventure_id):
		with self._connect() as conn:
			conn.execute(
				"INSERT OR IGNORE INTO web_adventure_members (adventure_id, user_id) VALUES (?, ?)",
				(adventure_id, user_id)
			)

	def is_member(self, user_id, adventure_id):
		with self._connect() as conn:
			row = conn.execute(
				"SELECT 1 FROM web_adventure_members WHERE adventure_id = ? AND user_id = ?",
				(adventure_id, user_id)
			).fetchone()
		return row is not None

	def member_names(self, adventure_id):
		with self._connect() as conn:
			rows = conn.execute("""
				SELECT u.username
				FROM web_adventure_members m JOIN web_users u ON u.id = m.user_id
				WHERE m.adventure_id = ? ORDER BY u.username COLLATE NOCASE
			""", (adventure_id,)).fetchall()
		return [row["username"] for row in rows]

	def add_adventure_owner(self, user_id, adventure_id):
		with self._connect() as conn:
			conn.execute(
				"INSERT INTO web_adventure_owners (adventure_id, user_id) VALUES (?, ?)",
				(adventure_id, user_id)
			)

	def is_adventure_owner(self, user_id, adventure_id):
		with self._connect() as conn:
			row = conn.execute(
				"SELECT 1 FROM web_adventure_owners WHERE adventure_id = ? AND user_id = ?",
				(adventure_id, user_id)
			).fetchone()
		return row is not None

	def remove_adventure(self, adventure_id):
		with self._connect() as conn:
			conn.execute("DELETE FROM web_adventure_members WHERE adventure_id = ?", (adventure_id,))
			conn.execute("DELETE FROM web_adventure_owners WHERE adventure_id = ?", (adventure_id,))

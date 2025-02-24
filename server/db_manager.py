import sqlite3
from contextlib import contextmanager
import threading
from typing import Optional
import time
import os

import uuid

from utils import get_timestamp


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _init_db(self):
        with self._get_conn() as conn:
            # Set WAL journal mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            
            # Set synchronous mode for better performance while maintaining durability
            conn.execute("PRAGMA synchronous=NORMAL")
            
            # Create the tasks table if it doesn't exist
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    taskid TEXT PRIMARY KEY,
                    start_timestamp BIGINT DEFAULT NULL,
                    end_timestamp BIGINT DEFAULT NULL,
                    report_path TEXT DEFAULT NULL
                )
            """)  # TODO change taskid from primary key autoincrement to a random, hard to guess string.

    @contextmanager
    def _get_conn(self):
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_path)
        try:
            yield self._local.conn
        except Exception as e:
            self._local.conn.rollback()
            raise e

    def create_task(self) -> str:
        """Creates a new task with a randomly generated UUID and returns the taskid"""
        task_id = str(uuid.uuid4())
        with self._get_conn() as conn:
            try:
                conn.execute("INSERT INTO tasks (taskid) VALUES (?)", (task_id,))
                conn.commit()
                return task_id
            except sqlite3.IntegrityError:
                # In the extremely unlikely event of a UUID collision, try again
                return self.create_task()

    def update_task_start(self, task_id: str):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET start_timestamp = ? WHERE taskid = ?",
                (get_timestamp(), task_id)
            )
            conn.commit()

    def update_task_end(self, task_id: str):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET end_timestamp = ? WHERE taskid = ?",
                (get_timestamp(), task_id)
            )
            conn.commit()

    def set_report_path(self, task_id: str, path: str):
        """Set the absolute path where the report will be stored"""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET report_path = ? WHERE taskid = ?",
                (os.path.abspath(path), task_id)
            )
            conn.commit()

    def clear_report_path(self, task_id: str):
        """Clear the report path after consumption"""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET report_path = NULL WHERE taskid = ?",
                (task_id,)
            )
            conn.commit()

    def get_task_status(self, task_id: str) -> tuple[Optional[float], Optional[float], Optional[str]]:
        """Returns (start_timestamp, end_timestamp, report_path)"""
        with self._get_conn() as conn:
            result = conn.execute(
                "SELECT start_timestamp, end_timestamp, report_path FROM tasks WHERE taskid = ?",
                (task_id,)
            ).fetchone()
            return result if result else (None, None, None)
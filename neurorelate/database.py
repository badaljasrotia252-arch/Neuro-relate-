import os
import sqlite3
import logging
from datetime import datetime
import dotenv

dotenv.load_dotenv()

logger = logging.getLogger("neurorelate.db")
logging.basicConfig(level=logging.INFO)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "your_password")
DB_NAME = os.getenv("DB_NAME", "neurorelate_db")
DB_PORT = int(os.getenv("DB_PORT", 3306))

# Path to SQLite fallback database
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB_PATH = os.path.join(BASE_DIR, "neurorelate.db")

_ENGINE = None  # 'mysql' or 'sqlite'

class SQLiteCursorWrapper:
    """Wrapper around sqlite3.Cursor to provide MySQL-compatible behavior."""
    def __init__(self, cursor, dictionary=False):
        self.cursor = cursor
        self.dictionary = dictionary

    def execute(self, sql, params=None):
        # Convert %s placeholder to ? for SQLite
        adapted_sql = sql.replace("%s", "?")
        if params is None:
            return self.cursor.execute(adapted_sql)
        # Convert datetime objects or tuples if necessary
        clean_params = []
        params_list = list(params) if isinstance(params, (list, tuple)) else [params]
        for p in params_list:
            if isinstance(p, datetime):
                clean_params.append(p.isoformat())
            else:
                clean_params.append(p)
        return self.cursor.execute(adapted_sql, clean_params)

    def executemany(self, sql, seq_of_params):
        adapted_sql = sql.replace("%s", "?")
        clean_seq = []
        for params in seq_of_params:
            clean_params = []
            params_list = list(params) if isinstance(params, (list, tuple)) else [params]
            for p in params_list:
                if isinstance(p, datetime):
                    clean_params.append(p.isoformat())
                else:
                    clean_params.append(p)
            clean_seq.append(clean_params)
        return self.cursor.executemany(adapted_sql, clean_seq)

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        if self.dictionary:
            return dict(row)
        return row

    def fetchall(self):
        rows = self.cursor.fetchall()
        if self.dictionary:
            return [dict(r) for r in rows]
        return rows

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    @property
    def rowcount(self):
        return self.cursor.rowcount

    @property
    def description(self):
        return self.cursor.description

    def close(self):
        self.cursor.close()

class SQLiteConnectionWrapper:
    """Wrapper around sqlite3.Connection to provide MySQL-compatible cursor creation."""
    def __init__(self, conn):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def cursor(self, dictionary=False, **kwargs):
        c = self.conn.cursor()
        return SQLiteCursorWrapper(c, dictionary=dictionary)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

def get_engine_type():
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE

    # Try connecting to MySQL first
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
            connection_timeout=2
        )
        conn.close()
        _ENGINE = "mysql"
        logger.info(f"Connected to MySQL server at {DB_HOST}:{DB_PORT}")
    except Exception as e:
        logger.info(f"MySQL unavailable ({e}). Falling back to SQLite at {SQLITE_DB_PATH}")
        _ENGINE = "sqlite"

    return _ENGINE

def get_db():
    """Returns an active database connection (MySQL or SQLite fallback)."""
    engine = get_engine_type()
    if engine == "mysql":
        try:
            import mysql.connector
            conn = mysql.connector.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                port=DB_PORT
            )
            return conn
        except Exception as e:
            logger.warning(f"Failed to connect to MySQL database '{DB_NAME}': {e}. Using SQLite fallback.")

    # SQLite connection
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return SQLiteConnectionWrapper(conn)

def init_db():
    """Initializes tables and indexes in the active database engine."""
    engine = get_engine_type()
    
    if engine == "mysql":
        try:
            import mysql.connector
            # Ensure database exists
            admin_conn = mysql.connector.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                port=DB_PORT
            )
            admin_cur = admin_conn.cursor()
            admin_cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            admin_cur.close()
            admin_conn.close()

            db = get_db()
            cur = db.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                upload_date DATETIME NOT NULL,
                extracted_text LONGTEXT,
                file_size INT DEFAULT 0,
                chunk_count INT DEFAULT 0
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                document_id INT NOT NULL,
                chunk_text TEXT NOT NULL,
                chunk_number INT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS query_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                source_document VARCHAR(255),
                created_at DATETIME NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            db.commit()
            cur.close()
            db.close()
            logger.info("MySQL database initialized successfully.")
            return
        except Exception as e:
            logger.warning(f"MySQL initialization failed ({e}). Falling back to SQLite.")

    # SQLite fallback table initialization
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        upload_date TIMESTAMP NOT NULL,
        extracted_text TEXT,
        file_size INTEGER DEFAULT 0,
        chunk_count INTEGER DEFAULT 0
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS document_chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL,
        chunk_text TEXT NOT NULL,
        chunk_number INTEGER NOT NULL,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS query_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        source_document TEXT,
        created_at TIMESTAMP NOT NULL
    );
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(document_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_filename ON documents(filename);")

    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"SQLite database initialized successfully at {SQLITE_DB_PATH}")

if __name__ == "__main__":
    init_db()

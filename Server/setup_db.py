import sqlite3

def setup_database():
    conn = sqlite3.connect('licenses.db')
    cursor = conn.cursor()

    cursor.execute('PRAGMA foreign_keys = ON;')

    # Table to store issued licenses
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_address TEXT NOT NULL UNIQUE,
            short_key TEXT NOT NULL UNIQUE,
            jwt_token TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            max_activations INTEGER NOT NULL,
            activations INTEGER DEFAULT 0,
            revoked INTEGER DEFAULT 0 CHECK(revoked IN (0,1)),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Trigger to auto-update updated_at
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS update_timestamp
        AFTER UPDATE ON licenses
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
            UPDATE licenses SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;
    ''')

    # Table to log activation attempts
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activations_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_address TEXT NOT NULL,
            short_key TEXT NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            success INTEGER NOT NULL CHECK(success IN (0,1)),
            reason TEXT,
            FOREIGN KEY (short_key) REFERENCES licenses(short_key) ON DELETE CASCADE
        )
    ''')

    # ✅ New table: approved MAC address list
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS valid_macs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_address TEXT NOT NULL UNIQUE
        )
    ''')

    # Indexes for performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mac ON licenses(mac_address)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_short_key ON licenses(short_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_log_short_key ON activations_log(short_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_log_mac ON activations_log(mac_address)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_approved_mac ON valid_macs(mac_address)')

    conn.commit()
    conn.close()
    print("Database and tables created or verified successfully.")

if __name__ == "__main__":
    setup_database()

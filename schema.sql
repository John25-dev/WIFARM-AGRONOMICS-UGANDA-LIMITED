CREATE TABLE clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    nin_encrypted TEXT UNIQUE,
    contact_phone TEXT,
    next_of_kin TEXT,
    lc1_doc_url TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER REFERENCES clients(id),
    principal_amount REAL,
    interest_rate REAL,
    balance REAL,
    arrears REAL,
    status TEXT DEFAULT 'ACTIVE'
);

CREATE TABLE branch_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_name TEXT,
    item_name TEXT,
    stock_count INTEGER,
    is_synced BOOLEAN DEFAULT FALSE,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

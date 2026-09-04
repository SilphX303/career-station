CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  kind TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  last_run TEXT,
  last_ok INTEGER,
  last_error TEXT
);
CREATE TABLE IF NOT EXISTS roles (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  external_id TEXT,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  company TEXT,
  location TEXT,
  remote_flag INTEGER NOT NULL DEFAULT 0,
  salary_min INTEGER,
  salary_max INTEGER,
  salary_text TEXT,
  description TEXT,
  posted_at TEXT,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  hash TEXT UNIQUE NOT NULL,
  filtered INTEGER NOT NULL DEFAULT 0,
  filter_reason TEXT,
  desc_quality TEXT,
  desc_reason TEXT,
  watch INTEGER NOT NULL DEFAULT 0,
  cluster_id INTEGER
);
CREATE TABLE IF NOT EXISTS scores (
  role_id INTEGER PRIMARY KEY REFERENCES roles(id),
  score INTEGER NOT NULL,
  reasons TEXT NOT NULL DEFAULT '[]',
  gaps TEXT NOT NULL DEFAULT '[]',
  scored_at TEXT NOT NULL,
  model TEXT,
  track TEXT
);
CREATE TABLE IF NOT EXISTS status (
  role_id INTEGER PRIMARY KEY REFERENCES roles(id),
  state TEXT NOT NULL DEFAULT 'new',
  changed_at TEXT NOT NULL,
  note TEXT,
  reason TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY,
  role_id INTEGER NOT NULL REFERENCES roles(id),
  channel TEXT NOT NULL,
  sent_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  role_id INTEGER NOT NULL REFERENCES roles(id),
  kind TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  content TEXT,
  requested_at TEXT NOT NULL,
  generated_at TEXT,
  model TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE TABLE IF NOT EXISTS research (
  role_id INTEGER PRIMARY KEY REFERENCES roles(id),
  status TEXT NOT NULL DEFAULT 'pending',
  brief TEXT,
  requested_at TEXT NOT NULL,
  generated_at TEXT,
  model TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_status ON research(status);
CREATE TABLE IF NOT EXISTS ingest (
  id INTEGER PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'pending',
  kind TEXT NOT NULL,            -- image | text
  text TEXT,                     -- pasted ad text, or the bot's extracted text
  url TEXT,
  images TEXT NOT NULL DEFAULT '[]',  -- filenames under /data/ingest
  result TEXT,                   -- structured fields from the bot
  role_id INTEGER REFERENCES roles(id),
  error TEXT,
  requested_at TEXT NOT NULL,
  done_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ingest_status ON ingest(status);
CREATE TABLE IF NOT EXISTS profile (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  markdown TEXT NOT NULL DEFAULT '',
  search_terms TEXT NOT NULL DEFAULT '[]',
  filters TEXT NOT NULL DEFAULT '{}',
  threshold INTEGER NOT NULL DEFAULT 75,
  cv_engineer TEXT NOT NULL DEFAULT '',
  cv_management TEXT NOT NULL DEFAULT '',
  watchlist TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_roles_last_seen ON roles(last_seen);
CREATE INDEX IF NOT EXISTS idx_status_state ON status(state);

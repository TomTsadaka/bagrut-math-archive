# -*- coding: utf-8 -*-
"""סכמת SQLite למאגר השאלות."""
import sqlite3, json, os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "bagrut.db")

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS papers (
  paper_id      TEXT PRIMARY KEY,   -- 35571_2025_08
  code          TEXT NOT NULL,      -- 35571
  year          INTEGER NOT NULL,
  moed          TEXT,               -- קיץ מועד א׳ / חורף / ...
  moed_code     TEXT,
  hebrew_moed   TEXT,               -- ב' תשפ"ה 2025
  units         INTEGER,            -- 3/4/5
  program       TEXT,               -- ישנה / רפורמה / חדשה
  part          INTEGER,
  source        TEXT,               -- ministry / wayback
  question_url  TEXT,
  solution_url  TEXT,
  question_pdf  TEXT,               -- local path
  solution_pdf  TEXT,
  n_pages       INTEGER,
  status        TEXT DEFAULT 'discovered',  -- discovered/fetched/extracted/failed
  note          TEXT
);

CREATE TABLE IF NOT EXISTS questions (
  question_id   TEXT PRIMARY KEY,   -- 35571_2025_08_q3
  paper_id      TEXT NOT NULL REFERENCES papers(paper_id),
  number        TEXT,               -- "3"
  chapter       TEXT,               -- פרק ראשון
  body          TEXT,               -- נוסח מלא (עברית + LaTeX)
  points        REAL,               -- ניקוד
  n_parts       INTEGER,
  has_figure    INTEGER DEFAULT 0,
  page_from     INTEGER,
  page_to       INTEGER,
  -- סיווג
  topic         TEXT,
  subtopics     TEXT,               -- JSON array
  difficulty    INTEGER,            -- 1-5
  qtype         TEXT,
  skills        TEXT,               -- JSON array
  est_minutes   INTEGER,
  needs_formula_sheet INTEGER DEFAULT 0,
  solution      TEXT,               -- פתרון רשמי אם נמצא
  confidence    REAL,
  cluster_id    TEXT,               -- לזיהוי שאלות חוזרות
  raw           TEXT                -- JSON גולמי מהמודל
);

CREATE TABLE IF NOT EXISTS parts (
  part_id       TEXT PRIMARY KEY,   -- 35571_2025_08_q3_a
  question_id   TEXT NOT NULL REFERENCES questions(question_id),
  letter        TEXT,               -- א / ב / ג
  body          TEXT,
  points        REAL,
  topic         TEXT,
  subtopics     TEXT,
  difficulty    INTEGER,
  solution      TEXT
);

CREATE INDEX IF NOT EXISTS idx_q_paper  ON questions(paper_id);
CREATE INDEX IF NOT EXISTS idx_q_topic  ON questions(topic);
CREATE INDEX IF NOT EXISTS idx_q_diff   ON questions(difficulty);
CREATE INDEX IF NOT EXISTS idx_p_year   ON papers(year);
CREATE INDEX IF NOT EXISTS idx_p_code   ON papers(code);
CREATE INDEX IF NOT EXISTS idx_p_units  ON papers(units);

CREATE TABLE IF NOT EXISTS figures (
  figure_id   TEXT PRIMARY KEY,
  paper_id    TEXT NOT NULL REFERENCES papers(paper_id),
  question_id TEXT,
  page        INTEGER,
  idx         INTEGER,
  file        TEXT,
  path        TEXT,
  w INTEGER, h INTEGER,
  x0 REAL, y0 REAL, x1 REAL, y1 REAL
);
CREATE INDEX IF NOT EXISTS idx_fig_paper ON figures(paper_id);
CREATE INDEX IF NOT EXISTS idx_fig_q     ON figures(question_id);

CREATE VIRTUAL TABLE IF NOT EXISTS questions_fts
  USING fts5(question_id UNINDEXED, body, topic, subtopics, tokenize='unicode61');
"""

def connect(path=DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con

def upsert_paper(con, p):
    cols = ["paper_id","code","year","moed","moed_code","hebrew_moed","units","program",
            "part","source","question_url","solution_url","question_pdf","solution_pdf",
            "n_pages","status","note"]
    vals = [p.get(c) for c in cols]
    con.execute(f"INSERT INTO papers ({','.join(cols)}) VALUES ({','.join('?'*len(cols))}) "
                f"ON CONFLICT(paper_id) DO UPDATE SET "
                + ",".join(f"{c}=COALESCE(excluded.{c},{c})" for c in cols[1:]), vals)

def upsert_question(con, q):
    cols = ["question_id","paper_id","number","chapter","body","points","n_parts",
            "has_figure","page_from","page_to","topic","subtopics","difficulty","qtype",
            "skills","est_minutes","needs_formula_sheet","solution","confidence",
            "cluster_id","raw"]
    vals = []
    for c in cols:
        v = q.get(c)
        if isinstance(v, (list, dict)): v = json.dumps(v, ensure_ascii=False)
        if isinstance(v, bool): v = int(v)
        vals.append(v)
    con.execute(f"INSERT OR REPLACE INTO questions ({','.join(cols)}) "
                f"VALUES ({','.join('?'*len(cols))})", vals)
    con.execute("INSERT INTO questions_fts (question_id, body, topic, subtopics) VALUES (?,?,?,?)",
                (q.get("question_id"), q.get("body") or "", q.get("topic") or "",
                 json.dumps(q.get("subtopics") or [], ensure_ascii=False)))

def upsert_part(con, p):
    cols = ["part_id","question_id","letter","body","points","topic","subtopics",
            "difficulty","solution"]
    vals = []
    for c in cols:
        v = p.get(c)
        if isinstance(v, (list, dict)): v = json.dumps(v, ensure_ascii=False)
        vals.append(v)
    con.execute(f"INSERT OR REPLACE INTO parts ({','.join(cols)}) "
                f"VALUES ({','.join('?'*len(cols))})", vals)

def stats(con):
    g = lambda q: con.execute(q).fetchone()[0]
    return {
        "papers": g("SELECT COUNT(*) FROM papers"),
        "fetched": g("SELECT COUNT(*) FROM papers WHERE status IN ('fetched','extracted')"),
        "extracted": g("SELECT COUNT(*) FROM papers WHERE status='extracted'"),
        "questions": g("SELECT COUNT(*) FROM questions"),
        "parts": g("SELECT COUNT(*) FROM parts"),
        "figures": g("SELECT COUNT(*) FROM figures"),
        "years": g("SELECT COUNT(DISTINCT year) FROM papers"),
        "year_min": g("SELECT MIN(year) FROM papers") or 0,
        "year_max": g("SELECT MAX(year) FROM papers") or 0,
    }


FIG_SCHEMA = """
CREATE TABLE IF NOT EXISTS figures (
  figure_id   TEXT PRIMARY KEY,
  paper_id    TEXT NOT NULL REFERENCES papers(paper_id),
  question_id TEXT,
  page        INTEGER,
  idx         INTEGER,
  file        TEXT,
  path        TEXT,
  w INTEGER, h INTEGER,
  x0 REAL, y0 REAL, x1 REAL, y1 REAL
);
CREATE INDEX IF NOT EXISTS idx_fig_paper ON figures(paper_id);
CREATE INDEX IF NOT EXISTS idx_fig_q     ON figures(question_id);
"""

def upsert_figure(con, f):
    cols = ["figure_id","paper_id","question_id","page","idx","file","path",
            "w","h","x0","y0","x1","y1"]
    con.execute(f"INSERT OR REPLACE INTO figures ({','.join(cols)}) "
                f"VALUES ({','.join('?'*len(cols))})", [f.get(c) for c in cols])

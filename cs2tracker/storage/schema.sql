-- Schéma SQLite du tracker. Toutes les écritures passent par des requêtes
-- paramétrées ; aucune interpolation de chaîne n'est utilisée.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL
);

-- Joueurs suivis --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS players (
    steamid64     TEXT PRIMARY KEY,
    persona_name  TEXT NOT NULL DEFAULT '',
    avatar_url    TEXT NOT NULL DEFAULT '',
    profile_url   TEXT NOT NULL DEFAULT '',
    country_code  TEXT,
    account_created INTEGER,
    is_favourite  INTEGER NOT NULL DEFAULT 0,
    notes         TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_players_favourite ON players(is_favourite);
CREATE INDEX IF NOT EXISTS idx_players_last_seen ON players(last_seen_at DESC);

-- Instantanés de statistiques -------------------------------------------------
CREATE TABLE IF NOT EXISTS stat_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    steamid64       TEXT    NOT NULL REFERENCES players(steamid64) ON DELETE CASCADE,
    captured_at     TEXT    NOT NULL,
    kills           INTEGER NOT NULL DEFAULT 0,
    deaths          INTEGER NOT NULL DEFAULT 0,
    rounds_played   INTEGER NOT NULL DEFAULT 0,
    matches_played  INTEGER NOT NULL DEFAULT 0,
    matches_won     INTEGER NOT NULL DEFAULT 0,
    time_played     INTEGER NOT NULL DEFAULT 0,
    headshot_kills  INTEGER NOT NULL DEFAULT 0,
    shots_fired     INTEGER NOT NULL DEFAULT 0,
    shots_hit       INTEGER NOT NULL DEFAULT 0,
    damage_done     INTEGER NOT NULL DEFAULT 0,
    mvps            INTEGER NOT NULL DEFAULT 0,
    kd_ratio        REAL    NOT NULL DEFAULT 0,
    headshot_rate   REAL    NOT NULL DEFAULT 0,
    accuracy        REAL    NOT NULL DEFAULT 0,
    payload_json    TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_snapshots_player_time
    ON stat_snapshots(steamid64, captured_at DESC);

-- Analyses anti-triche ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS analyses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    steamid64     TEXT    NOT NULL REFERENCES players(steamid64) ON DELETE CASCADE,
    analysed_at   TEXT    NOT NULL,
    score         REAL    NOT NULL,
    verdict       TEXT    NOT NULL,
    confidence    REAL    NOT NULL,
    confirmed_ban INTEGER NOT NULL DEFAULT 0,
    report_json   TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_analyses_player_time
    ON analyses(steamid64, analysed_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_score ON analyses(score DESC);

-- Matchs observés via GSI ------------------------------------------------------
CREATE TABLE IF NOT EXISTS matches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    map_name     TEXT NOT NULL DEFAULT '',
    mode         TEXT NOT NULL DEFAULT '',
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    score_ct     INTEGER NOT NULL DEFAULT 0,
    score_t      INTEGER NOT NULL DEFAULT 0,
    rounds_total INTEGER NOT NULL DEFAULT 0,
    summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_matches_started ON matches(started_at DESC);

CREATE TABLE IF NOT EXISTS match_players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id    INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    steamid64   TEXT    NOT NULL,
    name        TEXT    NOT NULL DEFAULT '',
    team        TEXT    NOT NULL DEFAULT '',
    kills       INTEGER NOT NULL DEFAULT 0,
    deaths      INTEGER NOT NULL DEFAULT 0,
    assists     INTEGER NOT NULL DEFAULT 0,
    mvps        INTEGER NOT NULL DEFAULT 0,
    adr         REAL    NOT NULL DEFAULT 0,
    headshot_rate REAL  NOT NULL DEFAULT 0,
    rounds      INTEGER NOT NULL DEFAULT 0,
    metrics_json TEXT   NOT NULL DEFAULT '{}',
    UNIQUE(match_id, steamid64)
);

CREATE INDEX IF NOT EXISTS idx_match_players_steamid ON match_players(steamid64);

CREATE TABLE IF NOT EXISTS match_rounds (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id     INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    winner       TEXT    NOT NULL DEFAULT '',
    ended_at     TEXT    NOT NULL,
    details_json TEXT    NOT NULL DEFAULT '{}',
    UNIQUE(match_id, round_number)
);

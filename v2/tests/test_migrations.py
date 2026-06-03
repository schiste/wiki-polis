"""Smoke tests for the two supported database setup paths."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from cachelib.file import FileSystemCache
from alembic.config import Config
from alembic.script import ScriptDirectory

from app import create_app
from db import (AdminRole, Argument, ArgumentSideState, ArgumentVote,
                Conversation, ConversationInvite, FeaturedStatement,
                Participant, Participation, db)


V2_ROOT = Path(__file__).resolve().parents[1]


def _head_revision() -> str:
    cfg = Config(str(V2_ROOT / 'migrations' / 'alembic.ini'))
    cfg.set_main_option('script_location', str(V2_ROOT / 'migrations'))
    return ScriptDirectory.from_config(cfg).get_current_head()


def _flask_env(db_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        'FLASK_DEBUG': '0',
        'DEV_LOGIN_USER': '',
        'DEV_FAKE_LOGIN': '',
        'DATABASE_URL': f'sqlite:///{db_path}',
        'SECRET_KEY': 'test-secret',  # pragma: allowlist secret
        'TRUSTED_HOSTS': 'wiki-polis.test',
        'RATELIMIT_STORAGE_URI': 'redis://localhost:6379/0',
        'POLIS_SERVER_URL': 'http://127.0.0.1:8003',
        'POLIS_ADMIN_EMAIL': 'test@example.org',
        'POLIS_ADMIN_PASSWORD': 'test',  # pragma: allowlist secret
    })
    return env


def _run_flask(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'flask', '--app', 'app', *args],
        cwd=V2_ROOT,
        env=_flask_env(db_path),
        check=True,
        text=True,
        capture_output=True,
    )


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table_name})')}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def _current_revision(conn: sqlite3.Connection) -> str:
    return conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]


def _assert_model_columns_present(conn: sqlite3.Connection) -> None:
    actual_tables = _tables(conn)
    for table_name, table in db.metadata.tables.items():
        assert table_name in actual_tables
        assert set(table.columns.keys()) <= _columns(conn, table_name)


def _assert_orm_can_use_schema(db_path: Path, tmp_path: Path) -> None:
    session_dir = tmp_path / f'sessions-{db_path.stem}'
    session_dir.mkdir()
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SQLALCHEMY_ENGINE_OPTIONS': {'connect_args': {'check_same_thread': False}},
        'WTF_CSRF_ENABLED': False,
        'RATELIMIT_ENABLED': False,
        'SECRET_KEY': 'test-secret',  # pragma: allowlist secret
        'SESSION_TYPE': 'cachelib',
        'SESSION_CACHELIB': FileSystemCache(str(session_dir)),
        'SESSION_PERMANENT': False,
    })

    with app.app_context():
        participant = Participant(
            mw_user_id=424242,
            mw_username=f'orm-{db_path.stem}',
            xid=f'{db_path.stem:0<64}'[:64],
        )
        conversation = Conversation(
            slug=f'orm-{db_path.stem}',
            polis_id=f'{db_path.stem[:6]:0<6}',
            title='ORM smoke conversation',
            active=True,
            access_policy='public',
        )
        db.session.add_all([participant, conversation])
        db.session.flush()

        participation = Participation(
            participant_id=participant.id,
            conversation_id=conversation.id,
            pseudonym=f'orm-{db_path.stem}',
            new_stmt_ids=[],
        )
        invite = ConversationInvite(
            conversation_id=conversation.id,
            mw_username=participant.mw_username,
        )
        role = AdminRole(
            participant_id=participant.id,
            conversation_id=conversation.id,
            role='moderator',
        )
        featured = FeaturedStatement(
            conversation_id=conversation.id,
            polis_statement_id=101,
            statement_text='Statement text',
            confirmed_by_admin=True,
        )
        db.session.add_all([participation, invite, role, featured])
        db.session.flush()

        argument = Argument(
            featured_statement_id=featured.id,
            proposer_id=participant.id,
            body='A concise argument.',
            side='pro',
        )
        db.session.add(argument)
        db.session.flush()

        vote = ArgumentVote(argument_id=argument.id, participant_id=participant.id)
        state = ArgumentSideState(
            participant_id=participant.id,
            featured_statement_id=featured.id,
            side='pro',
            argument_order=[argument.id],
            skipped=False,
        )
        db.session.add_all([vote, state])
        db.session.commit()

        saved = Participation.query.filter_by(pseudonym=f'orm-{db_path.stem}').one()
        assert saved.new_stmt_ids == []
        db.session.remove()


def test_init_db_creates_current_schema_and_stamps_head(tmp_path):
    db_path = tmp_path / 'fresh.db'

    result = _run_flask(db_path, 'init-db')

    assert 'Fresh database created and stamped at head.' in result.stdout
    with sqlite3.connect(db_path) as conn:
        assert _current_revision(conn) == _head_revision()
        assert {
            'public_username',
            'revealed_at',
            'new_stmt_ids',
        } <= _columns(conn, 'participations')
        assert {'closed_at', 'paused'} <= _columns(conn, 'conversations')
        assert 'hidden' in _columns(conn, 'arguments')
        _assert_model_columns_present(conn)
    _assert_orm_can_use_schema(db_path, tmp_path)


def test_legacy_schema_upgrades_to_current_head(tmp_path):
    db_path = tmp_path / 'legacy.db'
    _create_legacy_schema(db_path)

    _run_flask(db_path, 'db', 'upgrade')

    with sqlite3.connect(db_path) as conn:
        assert _current_revision(conn) == _head_revision()
        assert {
            'public_username',
            'revealed_at',
            'new_stmt_ids',
        } <= _columns(conn, 'participations')
        assert {'closed_at', 'paused'} <= _columns(conn, 'conversations')
        assert 'hidden' in _columns(conn, 'arguments')

        conn.execute(
            """
            INSERT INTO participations (
                participant_id, conversation_id, pseudonym, accepted_at
            ) VALUES (999, 999, 'legacy-user', CURRENT_TIMESTAMP)
            """
        )
        assert conn.execute(
            "SELECT new_stmt_ids FROM participations WHERE pseudonym = 'legacy-user'"
        ).fetchone()[0] == '[]'
        _assert_model_columns_present(conn)
    _assert_orm_can_use_schema(db_path, tmp_path)


def _create_legacy_schema(db_path: Path) -> None:
    """Create the pre-Alembic base schema expected by the first migration."""
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE participants (
                id INTEGER PRIMARY KEY,
                mw_user_id INTEGER NOT NULL UNIQUE,
                mw_username VARCHAR(255) NOT NULL,
                xid VARCHAR(64) NOT NULL UNIQUE,
                is_global_admin BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME
            );

            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY,
                slug VARCHAR(80) NOT NULL UNIQUE,
                polis_id VARCHAR(50) NOT NULL UNIQUE,
                title VARCHAR(255) NOT NULL,
                language VARCHAR(10) NOT NULL DEFAULT 'en',
                intro_text TEXT,
                outro_text TEXT,
                active BOOLEAN NOT NULL DEFAULT 1,
                access_policy VARCHAR(20) NOT NULL DEFAULT 'public',
                created_at DATETIME,
                phase_submission BOOLEAN NOT NULL DEFAULT 0,
                phase_personal_results BOOLEAN NOT NULL DEFAULT 0,
                phase_argument_mapping BOOLEAN NOT NULL DEFAULT 0,
                phase_public_results BOOLEAN NOT NULL DEFAULT 0,
                argument_vote_method VARCHAR(50) NOT NULL DEFAULT 'kApproval',
                argument_vote_data JSON NOT NULL DEFAULT '{"K": 2}'
            );

            CREATE TABLE participations (
                id INTEGER PRIMARY KEY,
                participant_id INTEGER NOT NULL,
                conversation_id INTEGER NOT NULL,
                pseudonym VARCHAR(80) NOT NULL UNIQUE,
                accepted_at DATETIME NOT NULL,
                notify_email BOOLEAN NOT NULL DEFAULT 0,
                notify_talk_page BOOLEAN NOT NULL DEFAULT 0,
                UNIQUE(participant_id, conversation_id)
            );

            CREATE TABLE featured_statements (
                id INTEGER PRIMARY KEY,
                conversation_id INTEGER NOT NULL,
                polis_statement_id INTEGER NOT NULL,
                statement_text TEXT,
                suggested_by_system BOOLEAN NOT NULL DEFAULT 0,
                confirmed_by_admin BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME,
                UNIQUE(conversation_id, polis_statement_id)
            );

            CREATE TABLE arguments (
                id INTEGER PRIMARY KEY,
                featured_statement_id INTEGER NOT NULL,
                proposer_id INTEGER,
                body VARCHAR(280) NOT NULL,
                side VARCHAR(3) NOT NULL,
                created_at DATETIME
            );

            CREATE TABLE conversation_invites (
                id INTEGER PRIMARY KEY,
                conversation_id INTEGER NOT NULL,
                mw_username VARCHAR(255) NOT NULL,
                created_at DATETIME,
                UNIQUE(conversation_id, mw_username)
            );

            CREATE TABLE admin_roles (
                id INTEGER PRIMARY KEY,
                participant_id INTEGER NOT NULL,
                conversation_id INTEGER NOT NULL,
                role VARCHAR(9) NOT NULL,
                granted_at DATETIME,
                granted_by INTEGER,
                UNIQUE(participant_id, conversation_id, role)
            );

            CREATE TABLE argument_votes (
                id INTEGER PRIMARY KEY,
                argument_id INTEGER NOT NULL,
                participant_id INTEGER NOT NULL,
                value INTEGER,
                created_at DATETIME,
                UNIQUE(argument_id, participant_id)
            );

            CREATE TABLE argument_side_states (
                id INTEGER PRIMARY KEY,
                participant_id INTEGER NOT NULL,
                featured_statement_id INTEGER NOT NULL,
                side VARCHAR(3) NOT NULL,
                argument_order JSON NOT NULL DEFAULT '[]',
                skipped BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME,
                UNIQUE(participant_id, featured_statement_id, side)
            );
            """
        )

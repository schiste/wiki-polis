"""Tests for security headers, redirect safety, and dev DB isolation."""
import os
from unittest.mock import patch

from db import Conversation, Participation, db


class _UpstreamResponse:
    def __init__(self, status_code=200, content=b'{}', headers=None, cookies=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {'Content-Type': 'application/json'}
        self.cookies = cookies or {}


def test_security_headers_on_every_response(client):
    """All responses carry the required security headers including CSP."""
    resp = client.get('/')
    assert resp.headers.get('X-Content-Type-Options') == 'nosniff'
    assert resp.headers.get('X-Frame-Options') == 'DENY'
    assert resp.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
    csp = resp.headers.get('Content-Security-Policy', '')
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_safe_redirect_blocks_absolute_external(app):
    from app import _safe_redirect
    with app.test_request_context('/'):
        assert _safe_redirect('https://evil.com/steal', '/') == '/'
        assert _safe_redirect('http://evil.com', '/') == '/'


def test_safe_redirect_blocks_protocol_relative(app):
    """//evil.com bypass is rejected."""
    from app import _safe_redirect
    with app.test_request_context('/'):
        assert _safe_redirect('//evil.com', '/') == '/'


def test_safe_redirect_allows_relative_paths(app):
    from app import _safe_redirect
    with app.test_request_context('/'):
        assert _safe_redirect('/admin', '/') == '/admin'
        assert _safe_redirect('/c/some-slug', '/') == '/c/some-slug'
        assert _safe_redirect('/accept/foo', '/') == '/accept/foo'


def test_admin_role_redirect_to_cannot_escape(app, admin_client, admin_participant, participant):
    """redirect_to field in role forms is sanitised through _safe_redirect."""
    conv = Conversation(slug='sec-conv', polis_id='sec1234567',
                        title='Security Test Conv', active=True, access_policy='public')
    db.session.add(conv)
    db.session.commit()
    resp = admin_client.post('/admin/roles/add', data={
        'participant_id': participant.id,
        'conversation_id': conv.id,
        'role': 'moderator',
        'redirect_to': '//evil.com',
    })
    assert resp.status_code == 302
    assert 'evil.com' not in resp.headers['Location']


def test_dev_db_isolation_refuses_non_sqlite(tmp_path):
    """create_app raises RuntimeError when DEV_DATABASE_URL is not sqlite://."""
    env = {
        'FLASK_DEBUG': '1',
        'DEV_LOGIN_USER': 'testuser',
        'DEV_DATABASE_URL': 'mysql://prod-host/db',
        # Make sure we don't collide with real secrets
        'SECRET_KEY': 'test',
    }
    import pytest
    with patch.dict(os.environ, env, clear=False):
        from app import create_app
        with pytest.raises(RuntimeError, match='sqlite'):
            create_app()


def test_dev_db_isolation_skipped_without_dev_login_user(tmp_path):
    """Without DEV_LOGIN_USER set, the isolation check is bypassed."""
    env_patch = {'DEV_LOGIN_USER': '', 'FLASK_DEBUG': '1'}
    with patch.dict(os.environ, env_patch, clear=False):
        from app import create_app
        # Should not raise — no isolation check when DEV_LOGIN_USER is empty
        a = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/iso.db',
            'SESSION_TYPE': 'filesystem',
            'SESSION_FILE_DIR': str(tmp_path),
        })
        assert a is not None


def test_proxy_delete_method_not_allowed(auth_client):
    """DELETE is not in the allowed proxy methods."""
    resp = auth_client.delete('/proxy/particiapi/api/conversations/')
    assert resp.status_code == 405


def test_proxy_blocks_conversation_without_participation(auth_client, conversation):
    """Logged-in users cannot proxy into conversations they have not joined."""
    conversation.phase_submission = True
    db.session.commit()

    with patch('app.requests.request') as mock_request:
        resp = auth_client.get(
            f'/proxy/particiapi/api/conversations/{conversation.polis_id}/statements/'
        )

    assert resp.status_code == 403
    mock_request.assert_not_called()


def test_proxy_blocks_invite_only_conversation_without_invite(auth_client):
    """Invite-only policy is enforced before forwarding to auth-disabled Particiapi."""
    conv = Conversation(
        slug='proxy-private',
        polis_id='prx1234567',
        title='Proxy Private',
        active=True,
        access_policy='invite_only',
        phase_submission=True,
    )
    db.session.add(conv)
    db.session.commit()

    with patch('app.requests.request') as mock_request:
        resp = auth_client.get(
            f'/proxy/particiapi/api/conversations/{conv.polis_id}/statements/'
        )

    assert resp.status_code == 403
    mock_request.assert_not_called()


def test_proxy_blocks_submission_phase_when_joined(auth_client, conversation, participant):
    """Joined users cannot submit/vote through the proxy when submission is off."""
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='proxy-tester',
    ))
    conversation.phase_submission = False
    db.session.commit()

    with patch('app.requests.request') as mock_request:
        resp = auth_client.get(
            f'/proxy/particiapi/api/conversations/{conversation.polis_id}/statements/'
        )

    assert resp.status_code == 403
    mock_request.assert_not_called()


def test_proxy_forwards_allowed_participant_conversation_path(
        auth_client, conversation, participant):
    """A participant in an open submission phase can use the needed proxy paths."""
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='proxy-member',
    ))
    conversation.phase_submission = True
    db.session.commit()

    with patch('app.requests.request',
               return_value=_UpstreamResponse()) as mock_request:
        resp = auth_client.get(
            f'/proxy/particiapi/api/conversations/{conversation.polis_id}/statements/'
        )

    assert resp.status_code == 200
    assert resp.get_json() == {}
    mock_request.assert_called_once()


def test_proxy_rejects_unknown_conversation_api_path(
        auth_client, conversation, participant):
    """Only the Particiapi paths used by wiki-polis are proxyable."""
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='proxy-known-path',
    ))
    conversation.phase_submission = True
    db.session.commit()

    with patch('app.requests.request') as mock_request:
        resp = auth_client.get(
            f'/proxy/particiapi/api/conversations/{conversation.polis_id}/unknown'
        )

    assert resp.status_code == 404
    mock_request.assert_not_called()


def test_proxy_results_disabled_returns_empty_without_forwarding(
        auth_client, conversation, participant):
    """Disabled results should not leak upstream data during client init."""
    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=conversation.id,
        pseudonym='proxy-results',
    ))
    conversation.phase_submission = True
    conversation.phase_public_results = False
    db.session.commit()

    with patch('app.requests.request') as mock_request:
        resp = auth_client.get(
            f'/proxy/particiapi/api/conversations/{conversation.polis_id}/results/'
        )

    assert resp.status_code == 200
    assert resp.get_json() == {}
    mock_request.assert_not_called()

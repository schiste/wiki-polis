"""Representative endpoint smoke tests by authorization class."""
from unittest.mock import patch

import pytest

from db import AdminRole, Conversation, Participation, db
from tests.conftest import login


@pytest.fixture
def smoke_conv(app):
    conv = Conversation(
        slug='smoke-conv',
        polis_id='smoke12345',
        title='Smoke Conversation',
        active=True,
        access_policy='public',
    )
    db.session.add(conv)
    db.session.commit()
    return conv


def test_public_endpoint_smoke(client, smoke_conv):
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'Smoke Conversation' in resp.data

    with patch('app.requests.get'):
        resp = client.get('/health')
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'ok'


def test_anonymous_protected_endpoint_smoke(client, smoke_conv):
    participant_resp = client.get(f'/c/{smoke_conv.slug}')
    admin_resp = client.get('/admin')

    assert participant_resp.status_code == 302
    assert '/login' in participant_resp.headers['Location']
    assert admin_resp.status_code == 302
    assert '/login' in admin_resp.headers['Location']


def test_participant_endpoint_smoke(auth_client, participant, smoke_conv):
    resp = auth_client.get(f'/accept/{smoke_conv.slug}')
    assert resp.status_code == 200

    resp = auth_client.get(f'/accept/{smoke_conv.slug}/pseudonyms')
    assert resp.status_code == 200
    assert 'pseudonyms' in resp.get_json()

    resp = auth_client.get(f'/c/{smoke_conv.slug}')
    assert resp.status_code == 302
    assert f'/accept/{smoke_conv.slug}' in resp.headers['Location']

    db.session.add(Participation(
        participant_id=participant.id,
        conversation_id=smoke_conv.id,
        pseudonym='steady-otter',
    ))
    db.session.commit()

    resp = auth_client.get(f'/c/{smoke_conv.slug}')
    assert resp.status_code == 200
    assert b'Nothing is available yet' in resp.data


def test_global_admin_endpoint_smoke(admin_client, smoke_conv):
    assert admin_client.get('/admin').status_code == 200
    assert admin_client.get(f'/admin/conversations/{smoke_conv.id}').status_code == 200
    assert admin_client.get(f'/admin/conversations/{smoke_conv.id}/invites').status_code == 200


def test_scoped_moderator_endpoint_smoke(client, participant, smoke_conv):
    db.session.add(AdminRole(
        participant_id=participant.id,
        conversation_id=smoke_conv.id,
        role='moderator',
    ))
    db.session.commit()
    login(client, 'testuser')

    assert client.get(f'/admin/conversations/{smoke_conv.id}').status_code == 200
    assert client.get(f'/admin/conversations/{smoke_conv.id}/invites').status_code == 200
    assert client.post(f'/admin/conversations/{smoke_conv.id}/pause').status_code == 403


def test_proxy_bridge_unsafe_method_smoke(auth_client):
    resp = auth_client.post('/proxy/particiapi/api/session')

    assert resp.status_code == 403

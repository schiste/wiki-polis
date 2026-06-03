"""Executable inventory for production route authorization policy."""
import pytest

from db import Conversation, db


KNOWN_POLICIES = {
    'public',
    'public-health',
    'public-oauth',
    'public-static',
    'session',
    'participant',
    'participant-argument',
    'participant-write',
    'conversation-moderator',
    'global-admin',
    'particiapi-bridge',
}


EXPECTED_ROUTE_POLICIES = {
    ('/', 'GET'): ('index', 'public'),
    ('/accept/<slug>', 'GET'): ('participant.accept', 'participant'),
    ('/accept/<slug>', 'POST'): ('participant.accept_post', 'participant-write'),
    ('/accept/<slug>/pseudonyms', 'GET'): (
        'participant.accept_pseudonyms',
        'participant',
    ),
    ('/admin', 'GET'): ('admin.admin', 'global-admin'),
    ('/admin/conversations/<int:conv_id>', 'GET'): (
        'admin.admin_conversation_detail',
        'conversation-moderator',
    ),
    ('/admin/conversations/<int:conv_id>/arguments/<int:arg_id>/delete', 'POST'): (
        'admin.admin_argument_delete',
        'conversation-moderator',
    ),
    ('/admin/conversations/<int:conv_id>/close', 'POST'): (
        'admin.admin_conversation_close',
        'global-admin',
    ),
    ('/admin/conversations/<int:conv_id>/edit', 'POST'): (
        'admin.admin_conversation_edit',
        'global-admin',
    ),
    ('/admin/conversations/<int:conv_id>/featured', 'GET'): (
        'admin.admin_conversation_featured',
        'conversation-moderator',
    ),
    ('/admin/conversations/<int:conv_id>/featured/<int:fs_id>/remove', 'POST'): (
        'admin.admin_featured_remove',
        'conversation-moderator',
    ),
    ('/admin/conversations/<int:conv_id>/featured/add', 'POST'): (
        'admin.admin_featured_add',
        'conversation-moderator',
    ),
    ('/admin/conversations/<int:conv_id>/featured/confirm', 'POST'): (
        'admin.admin_featured_confirm',
        'conversation-moderator',
    ),
    ('/admin/conversations/<int:conv_id>/invites', 'GET'): (
        'admin.admin_conversation_invites',
        'conversation-moderator',
    ),
    ('/admin/conversations/<int:conv_id>/invites/<int:invite_id>/remove', 'POST'): (
        'admin.admin_invite_remove',
        'conversation-moderator',
    ),
    ('/admin/conversations/<int:conv_id>/invites/add', 'POST'): (
        'admin.admin_invite_add',
        'conversation-moderator',
    ),
    ('/admin/conversations/<int:conv_id>/pause', 'POST'): (
        'admin.admin_conversation_pause',
        'global-admin',
    ),
    ('/admin/conversations/<int:conv_id>/phases', 'POST'): (
        'admin.admin_conversation_phases',
        'global-admin',
    ),
    ('/admin/conversations/<int:conv_id>/statements', 'GET'): (
        'admin.admin_conversation_statements',
        'conversation-moderator',
    ),
    ('/admin/conversations/<int:conv_id>/statements/<int:tid>/moderate', 'POST'): (
        'admin.admin_statement_moderate',
        'conversation-moderator',
    ),
    ('/admin/conversations/<int:conv_id>/statements/seed', 'POST'): (
        'admin.admin_statement_seed',
        'conversation-moderator',
    ),
    ('/admin/conversations/<int:conv_id>/strict-moderation', 'POST'): (
        'admin.admin_conversation_strict_moderation',
        'conversation-moderator',
    ),
    ('/admin/conversations/new', 'POST'): (
        'admin.admin_conversation_new',
        'global-admin',
    ),
    ('/admin/global-admins/<int:participant_id>/remove', 'POST'): (
        'admin.admin_global_admin_remove',
        'global-admin',
    ),
    ('/admin/global-admins/add', 'POST'): (
        'admin.admin_global_admin_add',
        'global-admin',
    ),
    ('/admin/roles/<int:role_id>/remove', 'POST'): (
        'admin.admin_role_remove',
        'global-admin',
    ),
    ('/admin/roles/add', 'POST'): ('admin.admin_role_add', 'global-admin'),
    ('/c/<slug>', 'GET'): ('participant.conversation', 'participant'),
    ('/c/<slug>/arguments/<int:arg_id>/hide', 'POST'): (
        'participant.argument_hide',
        'conversation-moderator',
    ),
    ('/c/<slug>/arguments/<int:arg_id>/unhide', 'POST'): (
        'participant.argument_unhide',
        'conversation-moderator',
    ),
    ('/c/<slug>/arguments/<int:arg_id>/unvote', 'POST'): (
        'participant.argument_unvote',
        'participant-argument',
    ),
    ('/c/<slug>/arguments/<int:arg_id>/vote', 'POST'): (
        'participant.argument_vote',
        'participant-argument',
    ),
    ('/c/<slug>/arguments/<int:fs_id>/<side>/skip', 'POST'): (
        'participant.argument_skip',
        'participant-argument',
    ),
    ('/c/<slug>/arguments/<int:fs_id>/submit', 'POST'): (
        'participant.argument_submit',
        'participant-argument',
    ),
    ('/c/<slug>/reveal', 'GET'): ('participant.reveal_identity', 'participant'),
    ('/c/<slug>/reveal', 'POST'): (
        'participant.reveal_identity_post',
        'participant-write',
    ),
    ('/c/<slug>/statements/new', 'POST'): (
        'proxy.conversation_statement_new',
        'particiapi-bridge',
    ),
    ('/health', 'GET'): ('health', 'public-health'),
    ('/login', 'GET'): ('login', 'public-oauth'),
    ('/logout', 'POST'): ('logout', 'session'),
    ('/oauth-callback', 'GET'): ('oauth_callback', 'public-oauth'),
    ('/proxy/particiapi/<path:pa_path>', 'GET'): (
        'proxy.proxy_particiapi',
        'particiapi-bridge',
    ),
    ('/proxy/particiapi/<path:pa_path>', 'POST'): (
        'proxy.proxy_particiapi',
        'particiapi-bridge',
    ),
    ('/proxy/particiapi/<path:pa_path>', 'PUT'): (
        'proxy.proxy_particiapi',
        'particiapi-bridge',
    ),
    ('/static/<path:filename>', 'GET'): ('static', 'public-static'),
}

EXAMPLE_ROUTE_VALUES = {
    '<slug>': 'matrix-conv',
    '<int:arg_id>': '1',
    '<int:conv_id>': '1',
    '<int:fs_id>': '1',
    '<int:invite_id>': '1',
    '<int:participant_id>': '1',
    '<int:role_id>': '1',
    '<int:tid>': '1',
    '<path:pa_path>': 'api/session',
    '<side>': 'pro',
}

PUBLIC_POLICIES = {
    'public',
    'public-health',
    'public-oauth',
    'public-static',
}


def _route_inventory(app):
    inventory = {}
    for rule in app.url_map.iter_rules():
        methods = sorted(rule.methods - {'HEAD', 'OPTIONS'})
        for method in methods:
            inventory[(rule.rule, method)] = rule.endpoint
    return inventory


def _example_path(route: str, conv: Conversation | None = None) -> str:
    path = route
    values = dict(EXAMPLE_ROUTE_VALUES)
    if conv is not None:
        values['<slug>'] = conv.slug
        values['<int:conv_id>'] = str(conv.id)

    for placeholder, value in values.items():
        path = path.replace(placeholder, value)
    return path


@pytest.fixture
def matrix_conv(app):
    conv = Conversation(
        slug='matrix-conv',
        polis_id='matrix1234',
        title='Matrix Conversation',
        active=True,
        access_policy='public',
    )
    db.session.add(conv)
    db.session.commit()
    return conv


def test_route_authorization_inventory_is_complete(app):
    actual = _route_inventory(app)

    assert actual == {
        route_key: endpoint
        for route_key, (endpoint, _policy) in EXPECTED_ROUTE_POLICIES.items()
    }


def test_route_authorization_inventory_uses_known_policy_labels():
    policies = {policy for _endpoint, policy in EXPECTED_ROUTE_POLICIES.values()}

    assert policies <= KNOWN_POLICIES


@pytest.mark.parametrize(
    ('route', 'method', 'policy'),
    [
        (route, method, policy)
        for (route, method), (_endpoint, policy) in EXPECTED_ROUTE_POLICIES.items()
        if policy not in PUBLIC_POLICIES
    ],
)
def test_protected_routes_redirect_anonymous_users(client, matrix_conv, route, method, policy):
    resp = client.open(_example_path(route, matrix_conv), method=method)

    assert resp.status_code == 302, policy
    assert '/login' in resp.headers['Location']


@pytest.mark.parametrize(
    ('route', 'method'),
    [
        (route, method)
        for (route, method), (_endpoint, policy) in EXPECTED_ROUTE_POLICIES.items()
        if policy == 'global-admin'
    ],
)
def test_global_admin_routes_forbid_regular_participants(auth_client, matrix_conv, route, method):
    resp = auth_client.open(_example_path(route, matrix_conv), method=method)

    assert resp.status_code == 403


@pytest.mark.parametrize(
    ('route', 'method'),
    [
        (route, method)
        for (route, method), (_endpoint, policy) in EXPECTED_ROUTE_POLICIES.items()
        if policy == 'conversation-moderator'
    ],
)
def test_moderator_routes_forbid_non_moderators(auth_client, matrix_conv, route, method):
    resp = auth_client.open(_example_path(route, matrix_conv), method=method)

    assert resp.status_code == 403

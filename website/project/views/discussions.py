# -*- coding: utf-8 -*-

import re

from flask import request
from modularodm import Q
from modularodm.exceptions import NoResultsFound

from framework.auth.decorators import collect_auth
from framework.auth.core import get_user

from website import mails
from website.project.decorators import (
    must_be_valid_project,
    must_have_permission,
    must_not_be_registration,
    must_be_contributor
)
from website.util.permissions import ADMIN
from website.models import Node


###############################################################################
# Internal Calls
###############################################################################


@must_be_valid_project
@must_have_permission(ADMIN)
@must_not_be_registration
def enable_discussions(node, **kwargs):
    node.discussions.enable(save=True)


@must_be_valid_project
@must_have_permission(ADMIN)
@must_not_be_registration
def disable_discussions(node, **kwargs):
    node.discussions.disable(save=True)


@must_be_valid_project
@collect_auth
@must_be_contributor
@must_not_be_registration
def set_subscription(node, auth, **kwargs):
    subscription = request.json.get('discussionsSub')
    subscribed = True if subscription == 'subscribed' else False
    if subscribed:
        node.discussions.subscribe_member(auth.user._id, save=True)
    else:
        node.discussions.unsubscribe_member(auth.user._id, save=True)


###############################################################################
# MailGun Calls
###############################################################################


def route_message(**kwargs):
    message = request.form
    target_address = message['To']
    node_id = re.search(r'[a-z0-9]*@', target_address).group(0)[:-1]
    sender_email = message['From']
    # allow for both "{email}" syntax and "{name} <{email}>" syntax
    if ' ' in sender_email:
        sender_email = re.search(r'<\S*>$', sender_email).group(0)[1:-1]

    sender = get_user(email=sender_email)
    if sender:
        sender = sender if sender.is_active else None
    node = Node.load(node_id)

    user_is_admin = 'admin' in node.get_permissions(sender)\
        if sender and node else False

    mail_params = {
        'to_addr': sender_email,
        'mail': mails.DISCUSSIONS_EMAIL_REJECTED,
        'target_address': target_address,
        'user': sender,
        'node_type': node.project_or_component if node else '',
        'node_url': node.absolute_url if node else '',
        'is_admin': user_is_admin
    }

    if not sender:
        reason = 'no_user'
    elif not node:
        reason = 'node_dne'
    elif node.is_deleted:
        reason = 'node_deleted'
    elif sender not in node.contributors:
        reason = 'no_access' if node.is_public else 'private_no_access'
    elif not node.discussions.is_enabled:
        reason = 'discussions_disabled'
    else:
        reason = ''

    if reason:
        mails.send_mail(reason=reason, **mail_params)

    # Any logging code should go here, since at this point the email has passed verification

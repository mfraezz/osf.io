# -*- coding: utf-8 -*-

import httplib as http
import pdb

from flask import request
from boto.exception import BotoServerError

from framework.exceptions import HTTPError
from framework.status import push_status_message
from framework.auth.decorators import must_be_logged_in

from website.project.decorators import must_have_permission
from website.project.decorators import must_not_be_registration
from website.project.decorators import must_have_addon

from website.addons.s3.api import S3Wrapper, has_access, does_bucket_exist, get_bucket_list
from website.addons.s3.utils import adjust_cors, create_osf_user

@must_be_logged_in
@must_have_addon('s3', 'user')
def s3_config_get(user_addon, **kwargs):
    """API that returns the serialized user settings."""
    return {
        'has_auth': user_addon.has_auth,
    }, http.OK

@must_be_logged_in
@must_have_addon('s3', 'node')
def s3_node_config_get(auth, node_addon, **kwargs):
    """API that returns the serialized user settings."""
    return {
        'result': s3_serialize_settings(auth, node_addon),
    }, http.OK

def s3_serialize_settings(auth, node_addon, **kwargs):
    """API that returns a dictionary representation of a
    S3NodeSettings record. 
    """
    #pdb.set_trace()

    if not node_addon.user_settings:
        return {
        'owner_url': node_addon.owner.url,
        'owner_name': None,
        'user_has_auth': bool(auth.user.get_addon('s3').secret_key),
        'is_registration': node_addon.owner.is_registration,
        'node_has_auth': False,
        'user_is_owner': False,
        'bucket_list': None
        }

    bucketList = [each.name for each in get_bucket_list(node_addon.user_settings)]
    bucketList.insert(0, '-----')

    return {
        'owner_url': node_addon.user_settings.owner.url,
        'owner_name': node_addon.user_settings.owner.fullname,
        'user_has_auth': bool(node_addon.user_settings) and node_addon.user_settings.has_auth,
        'is_registration': node_addon.owner.is_registration,
        'node_has_auth': node_addon.user_settings and node_addon.user_settings.has_auth,
        'user_is_owner': node_addon.user_settings.owner == auth.user,
        'bucket_list': bucketList
    }


def add_s3_auth(access_key, secret_key, user_settings):

    if not has_access(access_key, secret_key):
        return False

    user_name, access_key = create_osf_user(
        access_key, secret_key, user_settings.owner.family_name
    )

    user_settings.s3_osf_user = user_name
    user_settings.access_key = access_key['access_key_id']
    user_settings.secret_key = access_key['secret_access_key']

    user_settings.save()
    return True


@must_be_logged_in
@must_have_addon('s3', 'user')
def s3_authorize_user(user_addon, **kwargs):

    s3_access_key = request.json.get('access_key')
    s3_secret_key = request.json.get('secret_key')
    if not s3_access_key or not s3_secret_key:
        raise HTTPError(http.BAD_REQUEST)

    try:
        if not add_s3_auth(s3_access_key, s3_secret_key, user_addon):
            return {'message': 'Incorrect credentials'}, http.BAD_REQUEST
    except BotoServerError:
        #Note: Can't send back mark up :[
        return {
            'message': 'Could not access IAM. Please allow these keys permission.'
        }, http.BAD_REQUEST
    return {}


@must_have_permission('write')
@must_have_addon('s3', 'node')
def s3_authorize_node(auth, node_addon, **kwargs):

    user = auth.user

    s3_access_key = request.json.get('access_key')
    s3_secret_key = request.json.get('secret_key')
    if not s3_access_key or not s3_secret_key:
        raise HTTPError(http.BAD_REQUEST)

    user_settings = user.get_addon('s3')
    if user_settings is None:
        user.add_addon('s3')
        user_settings = user.get_addon('s3')

    if not add_s3_auth(s3_access_key, s3_secret_key, user_settings):
        return {'message': 'Incorrect credentials'}, http.BAD_REQUEST

    node_addon.authorize(user_settings, save=True)

    return {}


@must_have_permission('write')
@must_have_addon('s3', 'node')
@must_have_addon('s3', 'user')
def s3_node_import_auth(node_addon, user_addon, **kwargs):
    node_addon.authorize(user_addon, save=True)
    return {}


@must_have_permission('write')
@must_have_addon('s3', 'user')
@must_have_addon('s3', 'node')
@must_not_be_registration
def s3_node_settings(auth, user_addon, node_addon, **kwargs):

    user = auth.user
    node = node_addon.owner

    # Fail if user settings not authorized
    if not user_addon.has_auth:
        raise HTTPError(http.BAD_REQUEST)

    # If authorized, only owner can change settings
    if node_addon.user_settings and node_addon.user_settings.owner != user:
        raise HTTPError(http.BAD_REQUEST)

    # Claiming the node settings
    if not node_addon.user_settings:
        node_addon.user_settings = user_addon

    bucket = request.json.get('s3_bucket', '')

    if not bucket or not does_bucket_exist(user_addon.access_key, user_addon.secret_key, bucket):
        error_message = ('We are having trouble connecting to that bucket. '
                         'Try a different one.')
        return {'message': error_message}, http.BAD_REQUEST

    if bucket != node_addon.bucket:

        # Update node settings
        node_addon.bucket = bucket
        node_addon.save()

        node.add_log(
            action='s3_bucket_linked',
            params={
                'project': node.parent_id,
                'node': node._id,
                'bucket': node_addon.bucket,
            },
            auth=auth,
        )

        adjust_cors(S3Wrapper.from_addon(node_addon))

@must_be_logged_in
@must_have_addon('s3', 'user')
def s3_user_settings(user_addon, auth, **kwargs):
    """View for getting a JSON representation of the logged-in user's
    S3 user settings.
    """
    urls = {
        'create': api_url_for('s3_authorize_user'),
        'delete': api_url_for('s3_remove_user_settings')
    }
    info = user_addon.s3_info
    return {
        'result': {
            'userHasAuth': user_addon.has_auth,
            's3Name': info['display_name'] if info else None,
            'urls': urls,
        },
    }, http.OK

@must_have_permission('write')
@must_have_addon('s3', 'node')
@must_not_be_registration
def s3_remove_node_settings(auth, node_addon, **kwargs):
    node_addon.deauthorize(auth=auth, save=True)
    return {}




@must_be_logged_in
@must_have_addon('s3', 'user')
def s3_remove_user_settings(user_addon, **kwargs):
    success = user_addon.revoke_auth(save=True)
    if not success:
        push_status_message(
            'Your Amazon credentials were removed from the OSF, but we were '
            'unable to revoke your OSF information from Amazon. Your Amazon '
            'credentials may no longer be valid.'
        )
        return {'message': 'reload'}, http.BAD_REQUEST
    return {}

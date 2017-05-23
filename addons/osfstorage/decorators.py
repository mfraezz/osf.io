from __future__ import unicode_literals

from dateutil.parser import parse
import httplib
import functools

from flask import request
from modularodm.exceptions import NoResultsFound
from modularodm.storage.base import KeyExistsException

from addons.osfstorage.utils import make_error
from framework.auth.cas import parse_auth_header
from framework.auth.decorators import must_be_signed
from framework.exceptions import HTTPError
from osf.models import OSFUser as User, AbstractNode as Node, ApiOAuth2PersonalToken
from website.files import models
from website.files import exceptions
from website.project.decorators import (
    must_not_be_registration, must_have_addon,
)


def handle_odm_errors(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except NoResultsFound:
            raise HTTPError(httplib.NOT_FOUND)
        except KeyExistsException:
            raise HTTPError(httplib.CONFLICT)
        except exceptions.VersionNotFoundError:
            raise HTTPError(httplib.NOT_FOUND)
    return wrapped


def autoload_filenode(must_be=None, default_root=False):
    """Implies both must_have_addon osfstorage node and
    handle_odm_errors
    Attempts to load fid as a OsfStorageFileNode with viable constraints
    """
    def _autoload_filenode(func):
        @handle_odm_errors
        @must_have_addon('osfstorage', 'node')
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            node = kwargs['node']

            if 'fid' not in kwargs and default_root:
                file_node = kwargs['node_addon'].get_root()
            else:
                file_node = models.OsfStorageFileNode.get(kwargs.get('fid'), node)

            if must_be and file_node.kind != must_be:
                raise HTTPError(httplib.BAD_REQUEST, data={
                    'message_short': 'incorrect type',
                    'message_long': 'FileNode must be of type {} not {}'.format(must_be, file_node.kind)
                })

            kwargs['file_node'] = file_node

            return func(*args, **kwargs)

        return wrapped
    return _autoload_filenode

def autoload_fileversion(must_be=None, default_root=False, version_identifier='version', required=True):
    """Implies autoload_filenode
    Attempts to load version based on either a specifiable version kwarg or
    a `revision_at` kwarg iff using an `osf.admin`-scoped PAT
    """
    def _autoload_fileversion(func):
        @autoload_filenode(must_be=must_be, default_root=default_root)
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            file_node = kwargs['file_node']

            if request.args.get(version_identifier) and request.args.get('revision_at'):
                raise make_error(httplib.BAD_REQUEST, message_short='May specify either `version` or `revision_at`, not both.')

            if not request.args.get(version_identifier):
                version_id = None
            else:
                try:
                    version_id = int(request.args[version_identifier])
                except (TypeError, ValueError):
                    if required:
                        raise make_error(httplib.BAD_REQUEST, message_short='Version must be an integer if not specified')
                    version = None
                else:
                    version = file_node.get_version(version_id, required=required)

            if request.args.get('revision_at'):
                try:
                    revision_datetime = parse(request.args['revision_at'])
                except ValueError:
                    raise make_error(httplib.BAD_REQUEST, message_short='`revision_at` must be an ISO formatted date string.')
                else:
                    authorization = request.headers.get('Authorization', '')
                    access_token = parse_auth_header(authorization)
                    if not ApiOAuth2PersonalToken.objects.filter(token_id=access_token, scopes__contains='osf.admin').exists():
                        make_error(httplib.FORBIDDEN, message_short='Insufficient permissions to perform this action.')
                    version = file_node.get_version(version_at_date=revision_datetime)

            kwargs['file_version'] = version

            return func(*args, **kwargs)
        return wrapped
    return _autoload_fileversion


def waterbutler_opt_hook(func):

    @must_be_signed
    @handle_odm_errors
    @must_not_be_registration
    @must_have_addon('osfstorage', 'node')
    @functools.wraps(func)
    def wrapped(payload, *args, **kwargs):
        try:
            user = User.load(payload['user'])
            dest_node = Node.load(payload['destination']['node'])
            source = models.OsfStorageFileNode.get(payload['source'], kwargs['node'])
            dest_parent = models.OsfStorageFolder.get(payload['destination']['parent'], dest_node)

            kwargs.update({
                'user': user,
                'source': source,
                'destination': dest_parent,
                'name': payload['destination']['name'],
            })
        except KeyError:
            raise HTTPError(httplib.BAD_REQUEST)

        return func(*args, **kwargs)
    return wrapped

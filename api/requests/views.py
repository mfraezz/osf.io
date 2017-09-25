# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from rest_framework import generics
from rest_framework import permissions
from rest_framework.exceptions import NotFound

from framework.auth.oauth_scopes import CoreScopes
from osf.models import UserRequest

from api.base.views import JSONAPIBaseView
from api.base import permissions as base_permissions
from api.requests.permissions import MustNotBeContributorToCreateRequest, HasTargetOrRequestPermission
from api.requests.serializers import UserRequestSerializer

class RequestMixin(object):
    def get_user_request(self):
        try:
            user_request = UserRequest.objects.get(id=self.kwargs.get('request_id'))
        except UserRequest.DoesNotExist:
            raise NotFound(
                detail='No request matching that request_id could be found'
            )
        self.check_object_permissions(self.request, user_request)
        return user_request

class RequestDetail(JSONAPIBaseView, generics.RetrieveUpdateAPIView, RequestMixin):
    permission_classes = (
        permissions.IsAuthenticatedOrReadOnly,
        base_permissions.TokenHasScope,
        HasTargetOrRequestPermission
    )

    required_read_scopes = [CoreScopes.REQUEST_READ]
    required_write_scopes = [CoreScopes.REQUEST_WRITE]

    serializer_class = UserRequestSerializer
    view_category = 'user-requests'
    view_name = 'user-request-detail'

    def get_object(self):
        return self.get_user_request()

class RequestCreate(JSONAPIBaseView, generics.CreateAPIView, RequestMixin):
    permission_classes = (
        permissions.IsAuthenticated,
        base_permissions.TokenHasScope,
        MustNotBeContributorToCreateRequest
    )

    required_read_scopes = [CoreScopes.NULL]
    required_write_scopes = [CoreScopes.REQUEST_WRITE]

    serializer_class = UserRequestSerializer
    view_category = 'user-requests'
    view_name = 'user-request-create'

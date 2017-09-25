# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django.utils import timezone
from include import IncludeManager
from transitions import Machine

from api.requests import workflows
from osf.models.base import BaseModel
from osf.utils.fields import NonNaiveDateTimeField
from website.util import permissions


class UserRequest(BaseModel):
    __requests_machine = None
    objects = IncludeManager()

    creator = models.ForeignKey('OSFUser', related_name='submitted_requests')
    request_type = models.CharField(max_length=31, choices=workflows.RequestTypes.choices())
    current_state = models.CharField(max_length=31, choices=workflows.States.choices())
    message = models.TextField(null=True, blank=True)

    created = NonNaiveDateTimeField(db_index=True, auto_now_add=True)
    modified = NonNaiveDateTimeField(db_index=True, auto_now=True)
    last_transitioned = NonNaiveDateTimeField(null=True, blank=True, db_index=True)

    @property
    def machine(self):
        if not self.__requests_machine:
            self.__requests_machine = UserRequestMachine(self, 'current_state')
        return self.__requests_machine

    def resolve_access_request(self, user, approved):
        if approved:
            self.target.add_contributor(
                self.creator,
                permissions=[permissions.READ],
                auth=user.auth
            )


class RequestableMixin(models.Model):

    class Meta:
        abstract = True

    user_requests = models.ForeignKey('UserRequest', related_name='target')
    requests_allowed = models.BooleanField(default=True)

    def submit_request(self, request):
        self.user_requests.add(request)
        request.submit()


class UserRequestMachine(Machine):

    def __init__(self, user_request, state_attr):
        self.user_request = user_request
        self.__state_attr = state_attr
        super(UserRequestMachine, self).__init__(
            states=[s.value for s in workflows.States],
            transitions=workflows.TRANSITIONS,
            initial=self.state,
            send_event=True,
            prepare_event=['initialize_machine'],
            ignore_invalid_triggers=True,
        )

    @property
    def state(self):
        return getattr(self.user_request, self.__state_attr)

    @state.setter
    def state(self, value):
        setattr(self.user_request, self.__state_attr, value)

    def update_last_transitioned(self, ev):
        self.user_request.last_transitioned = timezone.now()

    def save_changes(self, ev):
        self.user_request.save()

    def resolve_response(self, ev):
        resolver = getattr(self.user_request, 'resolve_{}_request'.format(self.user_request.request_type))
        user = ev.kwargs.get('user')
        approved = ev.state.name == workflows.States.APPROVED.value
        resolver(self.user_request, user, approved)

    def notify_request(self, ev):
        # TODO
        pass

    def notify_approve(self, ev):
        # add_contributor notifies via email
        pass

    def notify_deny(self, ev):
        # TODO
        pass

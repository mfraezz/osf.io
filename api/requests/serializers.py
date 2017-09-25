from rest_framework import serializers as ser

from api.base.serializers import JSONAPISerializer, LinksField, DateByVersion
from api.requests import workflows
from osf.models import UserRequest


class UserRequestSerializer(JSONAPISerializer):
    class Meta:
        type_ = 'user-requests'

    filterable_fields = frozenset([
        'creator',
        'request_type',
        'current_state',
        'created',
        'id'
    ])
    id = ser.CharField(read_only=True)
    request_type = ser.ChoiceField(required=True, choices=workflows.RequestTypes.choices())
    current_state = ser.ChoiceField(required=False, choices=workflows.States.choices())
    message = ser.CharField(required=False, allow_blank=True, max_length=65535)
    created = DateByVersion(read_only=True)
    modified = DateByVersion(read_only=True)
    last_transitioned = DateByVersion(read_only=True)

    #TODO: somehow
    # target = WeirdGenericRelationField?

    links = LinksField({
        'self': 'get_absolute_url',
        'target': 'get_target_url'
    })

    def get_absolute_url(self, obj):
        pass

    def get_target_url(self, obj):
        pass

    def create(self, validated_data):
        # TODO: validation
        initial_state = workflows.States.INITIAL.value
        user_request = UserRequest.objects.create(current_state=initial_state, **validated_data)
        target = self.get_target()
        target.submit_request(user_request)

    def update(self, instance, validated_data):
        # TODO: validation
        pass


from enum import Enum, unique

# TODO: Dedupe when #7708 goes in
class ChoiceEnum(Enum):
    @classmethod
    def choices(cls):
        return tuple((v, unicode(v).title()) for v in cls.values())

    @classmethod
    def values(cls):
        return tuple(c.value for c in cls)

@unique
class RequestTypes(ChoiceEnum):
    ACCESS = 'access'

@unique
class States(ChoiceEnum):
    INITIAL = 'initial'
    REQUESTED = 'requested'
    APPROVED = 'approved'
    DENIED = 'denied'

@unique
class Triggers(ChoiceEnum):
    REQUEST = 'request'
    APPROVE = 'approve'
    DENY = 'deny'

TRANSITIONS = [
    {
        'trigger': Triggers.REQUEST.value,
        'source': [States.INITIAL.value],
        'dest': States.REQUESTED.value,
        'after': ['update_last_transitioned', 'notify_request', 'save_changes']
    }, {
        'trigger': Triggers.APPROVE.value,
        'source': [States.REQUESTED.value],
        'dest': States.APPROVED.value,
        'after': ['update_last_transitioned', 'resolve_response', 'notify_approve', 'save_changes']
    }, {
        'trigger': Triggers.DENY.value,
        'source': [States.REQUESTED.value],
        'dest': States.DENIED.value,
        'after': ['update_last_transitioned', 'resolve_response', 'notify_deny', 'save_changes']
    },
    # TODO: [PRODUCT-395]
    #{
    #    'trigger': Triggers.REQUEST.value,
    #    'source': [States.DENIED.value],
    #    'dest': States.REQUESTED.value,
    #    'conditions': ['is_eligible_for_resubmit'],
    #    'after': [] # TODO
    #}
]

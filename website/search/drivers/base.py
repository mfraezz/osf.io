import abc
import logging

logger = logging.getLogger(__name__)


class SearchDriver(object):

    __metaclass__ = abc.ABCMeta

    INDEXABLE_TYPES = (
        'registrations',
    )

    def __init__(self, warnings=True):
        self._warnings = warnings

    @abc.abstractmethod
    def teardown(self, types=None):
        raise NotImplementedError()

    @abc.abstractproperty
    def remove(self, model_instance):
        raise NotImplementedError()

    ### Search API  ###

    @abc.abstractmethod
    def search(self, query, index=None, doc_type=None, raw=None, refresh=False):
        raise NotImplementedError()

    ### /Search API  ###

from __future__ import absolute_import
from __future__ import unicode_literals

import abc
import logging
from md5 import md5
from time import time

from django.db.models import Count
from raven.contrib.django.raven_compat.models import client

from osf.models import RegistrationSchema
from website.search import exceptions
from website.search.generators.elastic.actions import RegistrationActionGenerator

logger = logging.getLogger(__name__)

DOC_TYPE = '_doc'
NODE_LIKE_MAPPINGS = {
    'type': {'index': True, 'type': 'keyword'},
    'category': {'index': True, 'type': 'keyword'},
    'title': {
        'index': True,
        'type': 'text',
        'fields': {
            'en': {
                'type': 'text',
                'analyzer': 'english',
            }
        }
    },
    'description': {
        'index': True,
        'type': 'text',
        'fields': {
            'en': {
                'type': 'text',
                'analyzer': 'english',
            }
        }
    },
    'tags': {'index': True, 'type': 'keyword', 'normalizer': 'tags'},
    'license': {
        'properties': {
            'id': {'index': True, 'type': 'keyword'},
            'name': {'index': True, 'type': 'keyword'},
            'year': {'index': True, 'type': 'date'},
        }
    }
}


class AbstractMappingGenerator(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def build_mapping(self):
        raise NotImplementedError()

    @abc.abstractproperty
    def alias_key(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def _get_action_generator(self, index=None):
        raise NotImplementedError()

    @classmethod
    @abc.abstractmethod
    def _migrate(cls):
        # Instantiates instance(s) and migrates
        raise NotImplementedError()

    @property
    def index(self):
        if not self._index:
            resp = self._client.indices.get_alias(name='{}*'.format(self.alias_key), ignore_unavailable=True, ignore=[404])
            if resp:
                self._index = resp.keys()[0]
        return self._index

    def build_normalizer(self):
        return {
            'tags': {
                'type': 'custom',
                'char_filter': [],
                'filter': ['lowercase', 'preserve_asciifolding']
            }
        }

    @property
    def type(self):
        return DOC_TYPE

    @property
    def index_settings(self):
        return {
            'settings': {
                # TODO
                'index.number_of_shards': 1,
                'index.number_of_replicas': 0,
                # 'index.shard.check_on_startup': False,
                # 'index.refresh_interval': -1,
                # 'index.gc_deletes': 0,
                # 'index.translog.sync_interval': '1s',
                # 'index.translog.durability': 'async',
                'analysis': {
                    'normalizer': self.build_normalizer(),
                    'analyzer': {
                        'default': {
                            'tokenizer': 'standard',
                            'filter': ['lowercase', 'preserve_asciifolding', 'standard'],
                        }
                    },
                    'filter': {
                        'preserve_asciifolding': {
                            'type': 'asciifolding',
                            'preserve_original': True,
                        }
                    }
                }
            },
            'mappings': {self.type: self.build_mapping()}
        }

    def __init__(self, driver, **kwargs):
        self._driver = driver
        self._client = driver._client
        self._index = kwargs.get('index', None)

    def migrate(self, **kwargs):
        self._before_migrate()

        old_index = self.index
        new_index = self._create_new_index()
        self._index = new_index

        self._populate_index(new_index)

        self._realias(new_index)
        logger.info('Cleaning up {}'.format(self.alias_key))
        self._remove_old_index(old_index)

        self._after_migrate()
        logger.info('Done migrating {}'.format(self.alias_key))

    def _before_migrate(self, **kwargs):
        logger.info('Preparing to migrate {}'.format(self.alias_key))
        if self._index:
            self._client.indices.put_settings(
                index=self.index,
                body={
                    'index.refresh_interval': '10s'
                },
            )

    def _after_migrate(self, **kwargs):
        self._client.indices.put_settings(
            index=self.index,
            body={
                'index.refresh_interval': '1s'
            },
        )

    def _populate_index(self, index):
        logger.info('Populating index {}'.format(index))
        actions = self._get_action_generator(index)
        try:
            self._driver._do_index(actions=actions)
        except Exception as e:
            client.captureException()
            logger.exception('_populate_index encountered an unexpected error')
            raise e
        logger.info('Done populating index {}'.format(index))

    def _create_new_index(self, **kwargs):
        index_name = '{}-{}'.format(self.alias_key, md5(str(time())).hexdigest())
        logger.info('Creating new index {}'.format(index_name))
        self._client.indices.create(
            index=index_name,
            body=self.index_settings
        )
        return index_name

    def _realias(self, index, **kwargs):
        return self._client.indices.put_alias(index=index, name=self.alias_key)

    def _remove_old_index(self, old_index, **kwargs):
        return self._client.indices.delete(index=old_index, ignore=[404])


class RegistrationMappingGenerator(AbstractMappingGenerator):

    @classmethod
    def _migrate(cls, driver):
        for schema in RegistrationSchema.objects.annotate(rc=Count('abstractnode')).filter(rc__gte=1).all():
            cls(driver, schema=schema).migrate()

    def __init__(self, *args, **kwargs):
        self._schema = kwargs.pop('schema', None)
        if not self._schema:
            raise exceptions.SearchException('RegistrationMappingGenerators must be instantiated with a "schema" kwarg')
        if not isinstance(self._schema, RegistrationSchema):
            raise TypeError('"schema" must be a RegistrationSchema instance')
        super(RegistrationMappingGenerator, self).__init__(*args, **kwargs)

    def _get_action_generator(self, index=None, initial_query=None):
        index = index or self._index
        initial_query = initial_query or {'registered_schema': self._schema.id}
        return RegistrationActionGenerator(index, self.type, initial_query=initial_query)

    @property
    def alias_key(self):
        return 'osf-registrations-{}'.format(self._schema._id)

    def build_mapping(self):
        return {
            'dynamic': 'strict',
            'properties': {
                'wikis': {
                    'dynamic': 'strict',
                    'type': 'object',
                    'properties': {
                        'page': {
                            'index': True,
                            'type': 'text',
                            'analyzer': 'english'
                        },
                        'content': {
                            'index': True,
                            'type': 'text',
                            'analyzer': 'english'
                        },
                    }
                },
                'registered_meta': {
                    'dynamic': 'strict',
                    'type': 'object',
                    'properties': {
                        block.block_id: {
                            'index': True,
                            'type': 'text' if block.block_type in ['string', 'osf-author-import'] else 'keyword',
                        } for block in self._schema.form_blocks.exclude(block_type='header')
                    }
                },
                'title': {
                    'index': True,
                    'type': 'text'
                },
                'contributors': {
                    'index': True,
                    'type': 'text'
                },
                'description': {
                    'index': True,
                    'type': 'text'
                },
                'parent_id': {
                    'index': True,
                    'type': 'text'
                },
                'tags': {
                    'index': True,
                    'type': 'keyword',
                    'normalizer': 'tags'
                },
                'affiliated_institutions': {
                    'index': True,
                    'type': 'keyword'
                },
                'date_created': {
                    'index': True,
                    'type': 'date'
                },
                'registered_date': {
                    'index': True,
                    'type': 'date'
                },
                'embargo_end_date': {
                    'index': True,
                    'type': 'date'
                },
            }
        }

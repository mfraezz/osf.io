from __future__ import absolute_import
from __future__ import unicode_literals

import copy
import logging
import time

import elasticsearch
from elasticsearch import helpers
from elasticsearch import TransportError

from api.base.settings import ELASTICSEARCH_DSL
from osf import models
from osf.utils.sanitize import unescape_entities

from website.search import exceptions
from website.search.drivers import base
from website.search import generators
from website.settings import ES6_MAX_CHUNK_BYTES

logger = logging.getLogger(__name__)
logging.getLogger('urllib3').setLevel(logging.WARN)
logging.getLogger('elasticsearch').setLevel(logging.WARN)
logging.getLogger('elasticsearch.trace').setLevel(logging.WARN)


class ElasticsearchDriver(base.SearchDriver):

    DOC_TYPE = '_doc'

    INDICES = {
        'registrations': {
            'doc_type': 'registration',
            'model': models.Registration,
            'index_tmpl': '{}-registrations',  # actually has '-<schema_id>' appended
            'action_generator': generators.RegistrationActionGenerator,
            'mapping_generator': generators.RegistrationMappingGenerator,
        },
    }

    def __init__(self, urls=None, index_prefix='osf', warnings=True, refresh=False, **kwargs):
        super(ElasticsearchDriver, self).__init__(warnings=warnings)
        urls = urls or ELASTICSEARCH_DSL['default']['hosts']
        self._refresh = refresh
        self._index_prefix = index_prefix
        self._client = elasticsearch.Elasticsearch(urls, **kwargs)

    def teardown(self, types=None):
        types = types or self.INDEXABLE_TYPES
        for type_, config in self.INDICES.items():
            if type_ not in types:
                continue
            self._client.indices.delete(index=config['index_tmpl'].format(self._index_prefix), ignore=[404])

    def _do_index(self, type_=None, query=None, actions=None):
        if not actions:
            # # TODO: this doesn't work due to 1 index per schema, rather than 1 for all registrations
            # assert type_ and query, 'Must receive type_ and query to create action generator'
            # actions = self.INDICES[type_]['action_generator'](
            #     self.INDICES[type_]['index_tmpl'].format(self._index_prefix),
            #     self.DOC_TYPE,
            #     initial_query=query,
            # )
            assert False

        stream = helpers.streaming_bulk(
            self._client,
            actions,
            max_chunk_bytes=ES6_MAX_CHUNK_BYTES,
            raise_on_error=False,
        )

        x = 0
        start = time.time()
        for ok, response in stream:
            if not ok and response.values()[0]['status'] != 404:
                raise exceptions.SearchException('Failed to index document {}'.format(response))
            # abusing that bool -> int so that documents that fail to get deleted
            # don't add to the total count
            x += int(ok)
            if x > 0 and x % 1000 == 0:
                print(x)
            assert len(response.values()) == 1
        logger.info('Indexed %d documents in %.02fs', x, time.time() - start)
        return x

    def migrate(self, models=None):
        models = models or self.INDICES.keys()
        for model in models:
            Mapper = self.INDICES[model]['mapping_generator']
            Mapper._migrate(self)

    def remove(self, instance):
        for config in self.INDICES.values():
            # Don't break out of this loop to handle special cases.
            # Namely projects/components
            if isinstance(instance, config['model']):
                self._client.delete(
                    ignore=[404],
                    doc_type=self.DOC_TYPE,
                    id=instance._id,
                    index=config['index_tmpl'].format(self._index_prefix)
                )

    # NOTE: the following implementation was more or less copypasta'd from elastic_search.py
    # TODO: Determine what's actually needed to be returned, adjust accordingly,
    # and update this
    def _get_aggregations(self, query, indices):
        query['aggregations'] = {
            'licenses': {
                'terms': {
                    'field': 'license.id'
                }
            },
            'counts': {
                'terms': {'field': 'type'}
            },
            'tag_cloud': {
                'terms': {'field': 'tags'}
            }
        }

        # TODO indexes/types
        res = self._client.search(
            size=0,
            body=query,
            index=indices,
        )

        ret = {}
        ret['licenses'] = {
            item['key']: item['doc_count']
            for item in res['aggregations']['licenses']['buckets']
        }
        ret['total'] = res['hits']['total']

        ret['counts'] = {
            x['key']: x['doc_count']
            for x in res['aggregations']['counts']['buckets']
            if x['key'] in self.ALIASES.keys()
        }
        ret['counts']['total'] = sum(ret['counts'].values())

        ret['tags'] = res['aggregations']['tag_cloud']['buckets']

        return ret

    # NOTE: the following implementation was more or less copypasta'd from elastic_search.py
    # TODO: Determine what's actually needed to be returned, adjust accordingly,
    # and update this
    def format_results(self, results):
        ret = []
        for result in results:
            if result.get('category') in {'project', 'component', 'registration', 'preprint'}:
                result = self.format_result(result, result.get('parent_id'))
            elif not result.get('category'):
                continue

            ret.append(result)
        return ret

    # NOTE: the following implementation was more or less copypasta'd from elastic_search.py
    # TODO: Determine what's actually needed to be returned, adjust accordingly,
    # and update this
    def format_result(self, result, parent_id=None):
        parent_info = self.load_parent(parent_id)
        formatted_result = {
            'contributors': result['contributors'],
            'wiki_link': result['url'] + 'wiki/',
            # TODO: Remove unescape_entities when mako html safe comes in
            'title': unescape_entities(result['title']),
            'url': result['url'],
            'is_component': False if parent_info is None else True,
            'parent_title': unescape_entities(parent_info.get('title')) if parent_info else None,
            'parent_url': parent_info.get('url') if parent_info is not None else None,
            'tags': result['tags'],
            'is_registration': (result['is_registration'] if parent_info is None
                else parent_info.get('is_registration')),
            'is_retracted': result['is_retracted'],
            'is_pending_retraction': result['is_pending_retraction'],
            'embargo_end_date': result['embargo_end_date'],
            'is_pending_embargo': result['is_pending_embargo'],
            'description': unescape_entities(result['description']),
            # TODO: Remove unescape_entities when mako html safeteape_entities(result['title']),
            'date_registered': result.get('registered_date'),
            'n_wikis': len(result['wikis'] or []),
            'license': result.get('license'),
            'affiliated_institutions': result.get('affiliated_institutions'),
            'preprint_url': result.get('preprint_url'),
        }

        return formatted_result

    def _doc_type_to_indices(self, doc_type):
        if not doc_type:
            return self._index_prefix + '*'
        for value in self.INDICES.values():
            if value['doc_type'] == doc_type:
                return value['index_tmpl'].format(self._index_prefix)
        raise NotImplementedError(doc_type)

    def search(self, query, doc_type=None, raw=False, refresh=False):
        if refresh or self._refresh:
            self._client.indices.refresh(self._doc_type_to_indices(doc_type))

        aggs_query = copy.deepcopy(query)

        indices = self._doc_type_to_indices(doc_type)

        for key in ['from', 'size', 'sort']:
            aggs_query.pop(key, None)

        try:
            del aggs_query['query']['filtered']['filter']
        except KeyError:
            pass

        try:
            aggregations = self._get_aggregations(aggs_query, indices)

            # Run the real query and get the results
            raw_results = self._client.search(index=indices, doc_type=self.DOC_TYPE, body=query)
        except TransportError as e:
            if e.info['error']['failed_shards'][0]['reason']['reason'].startswith('Failed to parse'):
                raise exceptions.MalformedQueryError(e.info['error']['failed_shards'][0]['reason']['reason'])
            raise exceptions.SearchException(e.info)

        results = [hit['_source'] for hit in raw_results['hits']['hits']]

        return {
            'aggs': {
                'total': aggregations['total'],
                'licenses': aggregations['licenses'],
            },
            'typeAliases': self.ALIASES,
            'tags': aggregations['tags'],
            'counts': aggregations['counts'],
            'results': raw_results['hits']['hits'] if raw else self.format_results(results),
        }

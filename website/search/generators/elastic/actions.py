from __future__ import absolute_import
from __future__ import unicode_literals

import abc
import logging
import re
import uuid

from django.db import connection
from django.db import transaction
from django.db.models import Exists, F, OuterRef, Subquery
from django.db.models.expressions import RawSQL
from django.db.models.functions import Coalesce

from addons.wiki.models import WikiPage, WikiVersion

from osf import models
from osf.utils.expressions import JSONBuildObject, ArrayAgg, JSONAgg

from website import settings


logger = logging.getLogger(__name__)


class AbstractActionGenerator(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def type(self):
        raise NotImplementedError

    @abc.abstractproperty
    def model(self):
        raise NotImplementedError

    @property
    def inital_queryset(self):
        if self._initial_query:
            return self.model.objects.filter(**self._initial_query)
        return self.model.objects.all()

    def __init__(self, index, doc_type, initial_query=None, chunk_size=1000):
        self._index = index
        self._doc_type = doc_type
        self._chunk_size = chunk_size
        self._remove = bool(initial_query)
        self._initial_query = initial_query or {}

    @abc.abstractmethod
    def build_query(self):
        raise NotImplementedError()

    def post_process(self, _id, doc):
        return doc

    def guid_for(self, model, ref='pk'):
        return Subquery(
            models.Guid.objects.filter(
                object_id=OuterRef(ref),
                content_type__app_label=model._meta.app_label,
                content_type__model=model._meta.concrete_model._meta.model_name,
            ).values('_id')[:1]
        )

    def _fetch_docs(self, query):
        with connection.cursor() as cursor:
            cursor_id = str(uuid.uuid4())
            query, params = query.query.sql_with_params()

            # Don't try this at home, kids
            cursor.execute('DECLARE "{}" CURSOR FOR {}'.format(cursor_id, query), params)

            # Should be able to use .iterator but it appears to be slower for whatever reason
            # TODO Investigate the above
            while True:
                cursor.execute('FETCH {} FROM "{}"'.format(self._chunk_size, cursor_id))
                rows = cursor.fetchall()

                if not rows:
                    return

                for row in rows:
                    if not row:
                        return
                    yield row[0]

    def __iter__(self):
        with transaction.atomic():
            qs = self.build_query()

            for doc in self._fetch_docs(qs):
                _id = doc.pop('_id')
                _source = self.post_process(_id, doc)

                yield {
                    '_id': _id,
                    '_op_type': 'index',
                    '_index': self._index,
                    '_type': self._doc_type,
                    '_source': _source,
                }


class NodeActionGenerator(AbstractActionGenerator):

    @abc.abstractproperty
    def category(self):
        raise NotImplementedError

    @abc.abstractmethod
    def _get_queryset(self):
        raise NotImplementedError

    @property
    def tags_query(self):
        return Coalesce(Subquery(
            models.AbstractNode.tags.through.objects.filter(
                tag__system=False,
                abstractnode_id=OuterRef('pk')
            ).annotate(
                tags=ArrayAgg(F('tag__name'))
            ).values('tags')
        ), [])

    @property
    def affiliated_institutions_query(self):
        return Coalesce(Subquery(
            models.Node.affiliated_institutions.through.objects.filter(
                abstractnode_id=OuterRef('pk')
            ).annotate(
                names=ArrayAgg(F('institution__name'))
            ).values('names')
        ), [])

    @property
    def contributors_query(self):
        return Subquery(
            models.Contributor.objects.filter(
                node_id=OuterRef('pk'),
                visible=True,
            ).annotate(
                names=ArrayAgg(
                    F('user__fullname'),
                    order_by=F('_order').asc()),
            ).order_by().values('names')
        )

    @property
    def parent_query(self):
        return Subquery(
            models.NodeRelation.objects.filter(
                is_node_link=False,
                child_id=OuterRef('pk')
            ).annotate(
                guid=self.guid_for(models.AbstractNode, 'parent_id')
            ).values('guid')[:1]
        )

    @property
    def wiki_query(self):
        return Subquery(WikiPage.objects.annotate(
            doc=JSONAgg(JSONBuildObject(
                page=F('page_name'),
                content=Subquery(WikiVersion.objects.filter(
                    wiki_page_id=OuterRef('pk')
                ).order_by('-created').values('content')[:1])
            ))
        ).filter(
            node_id=OuterRef('pk')
        ).values('doc'))

    def build_query(self):
        return self._get_queryset().annotate(
            doc=JSONBuildObject(**self._build_attributes())
        ).values('doc')

    def post_process(self, _id, doc):
        return doc

    def _build_attributes(self):
        return {
            '_id': self.guid_for(models.AbstractNode),
            # Node Attrs
            'title': F('title'),
            'description': F('description'),
            'date_created': F('created'),

            # Relations
            'wikis': self.wiki_query,
            'affiliated_institutions': self.affiliated_institutions_query,
            'contributors': self.contributors_query,
            'tags': self.tags_query,
            'parent_id': self.parent_query,  # TODO ???
        }

class RegistrationActionGenerator(NodeActionGenerator):
    type = 'registration'
    category = 'registration'
    model = models.Registration
    @property
    def retracted_query(self):
        return RawSQL(re.sub(r'\s+', ' ', '''COALESCE((
            WITH RECURSIVE ascendants AS (
                SELECT
                    N.id,
                    N.retraction_id
                FROM "{abstractnode}" AS N
                WHERE N.id = "{abstractnode}".id
            UNION ALL
                SELECT
                    N.id,
                    N.retraction_id
                FROM ascendants AS D
                    JOIN "{noderelation}" AS R ON R.child_id = D.id
                    JOIN "{abstractnode}" AS N ON N.id = R.parent_id
                WHERE D.retraction_id IS NULL AND R.is_node_link = FALSE
            ) SELECT
                RETRACTION.state = '{approved}' AS is_retracted
            FROM
                "{retraction}" AS RETRACTION
            WHERE
                RETRACTION.id = (SELECT retraction_id FROM ascendants WHERE retraction_id IS NOT NULL LIMIT 1)
            LIMIT 1
        ), FALSE)'''.format(
            abstractnode=models.AbstractNode._meta.db_table,
            approved=models.Retraction.APPROVED,
            noderelation=models.NodeRelation._meta.db_table,
            retraction=models.Retraction._meta.db_table,
        )), [])

    @property
    def multischema_query(self):
        # TODO: obviate this by normalizing data
        return RawSQL(re.sub(r'\s+', ' ', """
            SELECT abstractnode_id nid
            FROM osf_abstractnode_registered_schema
            GROUP BY abstractnode_id
              HAVING COUNT(abstractnode_id) > 1
        """), [])

    def _get_queryset(self):
        qs = self.inital_queryset.annotate(
            has_qa_tags=Exists(models.AbstractNode.tags.through.objects.filter(
                abstractnode_id=OuterRef('pk'),
                tag__name__in=settings.DO_NOT_INDEX_LIST['tags'],
            )),
            is_archiving_or_failed=Exists(models.ArchiveJob.objects.filter(
                dst_node_id=OuterRef('pk'),
            ).exclude(
                status='SUCCESS'
            )),
        ).filter(
            is_public=True,
            is_deleted=False,
            is_archiving_or_failed=False,
            has_qa_tags=False,
        ).exclude(
            spam_status=2
        ).exclude(
            id__in=self.multischema_query
        )
        for title in settings.DO_NOT_INDEX_LIST['titles']:
            qs = qs.exclude(title__icontains=title)

        if settings.SPAM_FLAGGED_REMOVE_FROM_SEARCH:
            qs = qs.exclude(spam_status=1)
        return qs

    def _build_attributes(self):
        return dict(
            super(RegistrationActionGenerator, self)._build_attributes(),
            registered_date=F('registered_date'),
            registered_meta=F('registered_meta'),
            is_retracted=self.retracted_query
        )

    def _post_process_reg_meta(self, meta):
        meta = meta.values()[0]  # Only ever one, exceptions are excluded
        INVALID_KEYS = ['embargoEndDate', 'registrationChoice']  # things that are put into registered_meta but should not be

        built = {}

        for k, v in meta.iteritems():
            if k in INVALID_KEYS:
                continue
            if isinstance(v, dict):
                v = v.get('value')
            if not isinstance(v, dict):
                built.update({k: v})
                continue
            if v.get('question', {}).get('value', False):
                built.update({'.'.join([k, 'question']): v['question']['value']})
            if v.get('uploader', {}).get('value', False):
                built.update({'.'.join([k, 'uploader']): v['uploader']['value']})

        return built

    def post_process(self, _id, doc):
        doc = super(RegistrationActionGenerator, self).post_process(_id, doc)

        if doc.pop('is_retracted'):
            doc['wikis'] = {}

        doc['registered_meta'] = self._post_process_reg_meta(doc.pop('registered_meta', {}))

        return doc

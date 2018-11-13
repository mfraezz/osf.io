from __future__ import unicode_literals
import logging

from django.core.management.base import BaseCommand

from website.search.drivers.elastic import ElasticsearchDriver

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """

    """
    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            'models',
            nargs='+',
            type=str,
            default=None
        )

    def handle(self, *args, **options):
        model_names = options.get('models', None)
        driver = ElasticsearchDriver()
        if model_names:
            assert set(model_names).issubset(driver.INDICES.keys())
        driver.migrate(models=model_names)

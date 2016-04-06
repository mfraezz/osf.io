import logging
import sys

from modularodm import Q

from framework.transactions.context import TokuTransaction
from website.app import init_app
from scripts import utils as script_utils

logger = logging.getLogger(__name__)

def get_targets():
    return #Model.find(Q('attr', 'op', value))

def migrate(targets, dry_run=True):
    # iterate over targets
    # log things

    if dry_run:
        raise RuntimeError('Dry run, transaction rolled back.')

def main():
    dry_run = False
    if '--dry' in sys.argv:
        dry_run = True
    if not dry_run:
        script_utils.add_file_logger(logger, __file__)
    init_app(set_backends=True, routes=False)
    with TokuTransaction():
        migrate(targets=get_targets(), dry_run=dry_run)

if __name__ == "__main__":
    main()

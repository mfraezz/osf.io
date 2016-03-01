import logging
import threading

from website import settings

_local = threading.local()
logger = logging.getLogger(__name__)

def postcommit_queue():
    if not hasattr(_local, 'postcommit_queue'):
        _local.postcommit_queue = []
    return _local.postcommit_queue

def postcommit_before_request():
    _local.postcommit_queue = []

def postcommit_after_request(response=None):
    try:
        if postcommit_queue():
            for task in postcommit_queue():
                task()
    except AttributeError:
        if not settings.DEBUG_MODE:
            logger.error('Post commit task queue not initialized')
    return response
def enqueue_postcommit_task(f):
    try:
        if f not in postcommit_queue():
            postcommit_queue().append(f)
    except RuntimeError:
        f()


handlers = {
    'before_request': postcommit_before_request,
    'after_request': postcommit_after_request,
}

# -*- coding: utf-8 -*-
import pdb

import os
import logging
import errno
import codecs

from framework.tasks import app as celery_app
from framework.flask import app as flask_app
from website import settings
import mfr
from mfr.core import RenderResult
from mfr.core import register_filehandlers
from mfr.exceptions import MFRError
from website.language import ERROR_PREFIX, STATA_VERSION_ERROR, BLANK_OR_CORRUPT_TABLE_ERROR

logger = logging.getLogger(__name__)

config = {}
#FileRenderer.STATIC_PATH = '/static/mfr'

# Register the file handlers
HERE = os.path.abspath(os.path.dirname(__file__))
mfr.config.from_pyfile(os.path.join(HERE, 'mfr_config.py'), silent=True)

# Update mfr config with static path and url
mfr.config.update({
    # Base URL for static files
    'STATIC_URL': os.path.join(flask_app.static_url_path, 'mfr'),
    # Where to save static files
    'STATIC_FOLDER': os.path.join(flask_app.static_folder, 'mfr'),
})

mfr.collect_static()

# Unable to render. Download the file to view it.
def render_mfr_error(err):
    """Display an error message on the page based on the error"""

    pre = "Unable to render. <a href='{download_path}'>Download</a> file to view it."
    msg = err.message
    return """
           <div class="osf-mfr-error">
           <p>{pre}</p>
           <p>{msg}</p>
           </div>
        """.format(**locals())


@celery_app.task(time_limit=settings.MFR_TIMEOUT)
def _build_rendered_html(file_path, cache_dir, cache_file_name, download_url):
    """ Render a file to html, build the assets list, and cache the resultant
    html to a cache file.

    :param file_path: path of file to be rendered
    :param cache_dir: location of directory to cache rendered files
    :param cache_file_name: name of file to cache to
    :param str download_url: relative url of file to be rendered
    """
    file_pointer = codecs.open(file_path)

    # Build path to cached content
    # Note: Ensures that cache directories have the same owner as the files
    # inside them
    ensure_path(cache_dir)
    cache_file_path = os.path.join(cache_dir, cache_file_name)


    with codecs.open(cache_file_path, 'w', 'utf-8') as write_file_pointer:
        # Render file

        logger.warn('attempting to render ' + file_path)
        try:
            result = _build_html(mfr.render(file_pointer, src=download_url))
            #pdb.set_trace()
        except Exception as err:
            result = render_mfr_error(err).format(download_path=download_url)
    
        # Close read pointer
        file_pointer.close()

        pdb.set_trace()

        # Cache rendered content
        write_file_pointer.write(result)

    os.remove(file_path)
    return True

#Expose render function
build_rendered_html = _build_rendered_html

if settings.USE_CELERY:
    build_rendered_html = _build_rendered_html.delay

def _build_css_asset(css_uri):
    """Wrap a css asset so it can be included on an html page"""
    return '<link rel="stylesheet" href={uri}/>'.format(uri=css_uri)

def _build_js_asset(js_uri):
    """Wrap a js asset so it can be included on an html page"""
    return '<script src="{uri}"></script>'.format(uri=js_uri)

def _build_html(render_result):
    """Build all of the assets and content into an html page"""
    if render_result.assets:
        css_list = render_result.assets.get('css') or []
        css_assets = "\n".join(
            [_build_css_asset(css_uri) for css_uri in css_list]
        )

        js_list = render_result.assets.get('js') or []
        js_assets = "\n".join(
            [_build_js_asset(js_uri) for js_uri in js_list]
        )
        #pdb.set_trace()
    else:
        css_assets = js_assets = ""

    rv = "{css}\n\n{js}\n\n{content}".format(
        css=css_assets,
        js=js_assets,
        content=render_result.content or "",
    )

    #pdb.set_trace()

    return rv

def ensure_path(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise

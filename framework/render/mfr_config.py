import sys

import mfr_audio
import mfr_image
import mfr_movie
import mfr_pdb
import mfr_pdf
import mfr_rst
import mfr_tabular

# Register each of the handlers
HANDLERS = [
    mfr_audio.Handler,
    mfr_image.Handler,
    mfr_movie.Handler,
    mfr_pdb.Handler,
    mfr_pdf.Handler,
    mfr_rst.Handler,
    mfr_tabular.Handler,
]

if sys.version_info > (2, 6):
#    logger.warn('importing mfr_ipynb')
    import mfr_ipynb
    HANDLERS.append(mfr_ipynb.Handler)

if sys.version_info < (3, 3):
#    logger.warn('importing mfr_docx, mfr_code_pygments')
    import mfr_docx
    import mfr_code_pygments
    HANDLERS.append(mfr_docx.Handler)
    HANDLERS.append(mfr_code_pygments.Handler)

# List of asset files that should be excluded if an mfr module would have
# included it, eg, jquery is already on the page and shouldn't be included again.
EXCLUDE_LIBS = [
    "jquery-1.7.min.js",
    "jquery.min.js",
]
MFR_TIMEOUT = 30000
import sys
import os

INTERP = os.path.expanduser("/var/www/u3511384/data/flaskenv/bin/python")
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import application
except Exception as e:
    import traceback
    _tb = traceback.format_exc()
    def application(environ, start_response):
        start_response('500 Internal Server Error', [('Content-Type', 'text/plain; charset=utf-8')])
        return [_tb.encode('utf-8')]
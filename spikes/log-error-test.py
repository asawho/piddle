import time, datetime
import os, sys, logging
from logging.handlers import RotatingFileHandler
from logging.handlers import TimedRotatingFileHandler
from logging.handlers import SMTPHandler

#Setup the loggers-------------------------------------------------
fileLogger = logging.getLogger('file')
fileLogger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s  %(message)s")
fh = TimedRotatingFileHandler("test.log", when="midnight", interval=1, backupCount=2)
sh = logging.StreamHandler(sys.stdout)
fh.setFormatter(fmt)
sh.setFormatter(fmt)
fileLogger.addHandler(fh)
fileLogger.addHandler(sh)
log = fileLogger
log.info('Starting...')

try:
    x = float("asdf")
except Exception as e:
    log.error(e, exc_info=True)

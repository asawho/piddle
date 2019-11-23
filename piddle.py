import bottle
import json
import threading
import time
import datetime
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from logging.handlers import TimedRotatingFileHandler
import controller
import config

#Setup the logger-------------------------------------------------
if not os.path.exists('data'):
    os.mkdir('data')
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    handlers=[
        #RotatingFileHandler (config.log_path, maxBytes=1024*1024, backupCount=1),
        #TimedRotatingFileHandler("data/piddle.log", when="m", interval=1, backupCount=5)
        TimedRotatingFileHandler("./data/piddle.log", when="midnight", interval=1, backupCount=5),
        logging.StreamHandler(sys.stdout)
    ])
log = logging.getLogger()
log.info('Starting...')

#Initialize the controller---------------------------------------
ctrl = controller.PidController()

#Setup the web API------------------------------------------------
app = bottle.Bottle()

@bottle.route('/profile/stop')
def webStopProfile():
    ctrl.resetToConfig()
    return { "msg" : 'Profile stopped' }

@bottle.route('/profile/start/<name>')
def webStartProfile(name):
    if ctrl.setModeProfile(name):
        return { "msg" : 'Profile started' }
    else:
        bottle.response.status=500
        return { "msg" : 'Unknown profile, could not start' }
    
@bottle.route('/state')
def webState():
    return json.dumps(ctrl.getState())

#Start it in daemon mode so that the web app dies when the pid loop does
threading.Thread(target=app.run, kwargs=dict(host=config.listening_ip, port=config.listening_port), daemon=True).start()

#Start the controller, make dang sure it is off at the end-------------------------------
try:
    ctrl.run_forever()
finally:
    ctrl.setModeOff()




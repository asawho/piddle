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
import operationConfig
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
        TimedRotatingFileHandler("./data/piddle.log", when="midnight", interval=1, backupCount=2),
        logging.StreamHandler(sys.stdout)
    ])
log = logging.getLogger()
log.info('Starting...')

#Verify the configs----------------------------------------------
errors=[]
def validateProfiles(profiles, errors):
    #Validate the profiles
    for key, profile in profiles.items():
        if len(profile)==0:
            errors.append("Profile {} has no steps.".format(key))
        for index, value in enumerate(profile):
            if "type" not in value:
                errors.append("Step {} of profile {} has no ramp type set.".format(index,key))
            else:
                if value["type"] not in ("rate", "time", "mode"):
                    errors.append("Step {} of profile {} has no unknown ramp type {} set.".format(index,key,value["type"]))

            if value["type"]!='off' and "target" not in value:
                errors.append("Step {} of profile {} has no target set.".format(index,key))

            if "value" not in value:
                errors.append("Step {} of profile {} has no value set.".format(index,key))

def validateAlerts(alerts, errors):
    #Validate the profiles
    for index, value in enumerate(alerts):
        if "target" not in value:
            errors.append("Alert {} has no target set.".format(index))

        if "latching" not in value:
            errors.append("Alert {} has no latching set.".format(index))

        if "activeLogicLevel" not in value:
            errors.append("Alert {} has no activeLogicLevel set.".format(index))

        if "alertOutput" not in value:
            errors.append("Alert {} has no alertOutput set.".format(index))

validateProfiles(config.profiles)
validateAlerts(config.alerts)
if len(errors):
    for err in errors: 
        self.log.error(err)
    raise Exception(errors)

#Initialize the controller---------------------------------------
ctrl = controller.PidController()

#Setup the web API------------------------------------------------
app = bottle.Bottle()
@bottle.route('/')
def indexHTML():
    return bottle.static_file('index.html', root='./')

@bottle.route('/mode/off')
def setModeOff():
    ctrl.setModeOff(updateOperationFile=True)
    return { "msg" : 'Mode -> Off' }

@bottle.route('/mode/manual/<output>')
def setModeManual(output):
    try:
        output=float(output)
    except:
        bottle.response.status=500
        return { "msg" : 'Could not convert manual output value to float' }    

    ctrl.setModeManual (output, updateOperationFile=True)
    return { "msg" : 'Mode -> Manual, Output: {}'.format(output) }

@bottle.route('/mode/setpoint/<setpoint>')
def setModeManual(setpoint):
    try:
        setpoint=float(setpoint)
    except:
        bottle.response.status=500
        return { "msg" : 'Could not convert setpoint value {} to float.'.format(setpoint) }    

    ctrl.setModeSetPoint (setpoint, updateOperationFile=True)
    return { "msg" : 'Mode -> Manual, Output: {}'.format(output) }

@bottle.route('/mode/profile/stop')
def webStopProfile():
    ctrl.resetToConfig()
    return { "msg" : 'Profile stopped' }

@bottle.route('/mode/profile/start/<name>')
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




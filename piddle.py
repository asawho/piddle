import bottle
import json
import threading
import time, datetime
import os, sys, logging
from logging.handlers import RotatingFileHandler
from logging.handlers import TimedRotatingFileHandler
from logging.handlers import SMTPHandler
import controller
import operationConfig
import config

#Setup the loggers-------------------------------------------------
if not os.path.exists('data'):
    os.mkdir('data')
fileLogger = logging.getLogger('file')
fileLogger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s  %(message)s")
fh = TimedRotatingFileHandler("./data/piddle.log", when="midnight", interval=1, backupCount=2)
sh = logging.StreamHandler(sys.stdout)
fh.setFormatter(fmt)
sh.setFormatter(fmt)
fileLogger.addHandler(fh)
fileLogger.addHandler(sh)
log = fileLogger
log.info('Starting...')

smtpLogger = logging.getLogger('smtp')
try:
    import smtpLogConfig
    smtphost = os.uname()[1].lower()
    smtpLogger.setLevel(logging.INFO)
    smtpLogger.addHandler(SMTPHandler(smtpLogConfig.mailhost, smtpLogConfig.fromaddr, smtpLogConfig.toaddrs, smtphost + ' alert', smtpLogConfig.credentials, smtpLogConfig.secure))
except ImportError:
    #If it fails to load, then the logger just logs to the console
    pass

# If we don't start up as off, give everyone a heads up.  This way if it reboots because of a power loss or 
# something you get alerted that it is coming back up hot.
operationConfig = operationConfig.OperationConfig()
operationConfig.checkForNewConfig()
if operationConfig.data["mode"]!="OFF":
    smtpLogger.info('Starting up in HOT in mode:{}, manualOutput:{}, setPointTarget:{}'.format(operationConfig.data["mode"],operationConfig.data["manualOutput"], operationConfig.data["setpointTarget"]))

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
                continue
            else:
                if value["type"] not in ("rate", "time", "mode"):
                    errors.append("Step {} of profile {} has no unknown ramp type {} set.".format(index,key,value["type"]))
                    continue

            if "value" not in value:
                errors.append("Step {} of profile {} has no value set.".format(index,key))
                continue

            if value["value"]!='off' and "target" not in value:
                errors.append("Step {} of profile {} has no target set.".format(index,key))
                continue

            # if value["type"]=='time' and value["value"]==0:
            #     errors.append("Step {} of profile {} has zero for time.".format(index,key))


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

validateProfiles(config.profiles, errors)
validateAlerts(config.alerts, errors)
if len(errors):
    for err in errors: 
        log.error(err)
    raise Exception(errors)

#Initialize the controller---------------------------------------
ctrl = controller.PidController()

#Setup the web API------------------------------------------------
app = bottle.Bottle()
@app.hook('after_request')
def enableCors():
    bottle.response.headers['Access-Control-Allow-Origin'] = '*'

@app.route('/')
def indexHTML():
    return bottle.static_file('index.html', root='./public')

@app.route('/assets/<filepath:path>')
def server_static(filepath):
    return bottle.static_file(filepath, root='./public/assets')

@app.route('/mode/off')
def setModeOff():
    ctrl.setModeOff(updateOperationFile=True)
    return { "msg" : 'Mode -> Off' }

@app.route('/mode/manual/<output>')
def setModeManual(output):
    try:
        output=float(output)
        if output < 0 or output > 1:
            raise Exception
    except:
        bottle.response.status=500
        return { "msg" : 'Could not convert manual output value to float between 0 and 1.' }    

    ctrl.setModeManual (output, updateOperationFile=True)
    return { "msg" : 'Mode -> Manual, Output: {}'.format(output) }

@app.route('/mode/setpoint/<setpoint>')
def setModeSetpoint(setpoint):
    try:
        setpoint=float(setpoint)
        if setpoint < 0 or setpoint > 2350:
            raise Exception
    except:
        bottle.response.status=500
        return { "msg" : 'Could not convert setpoint value {} to float between 0 and 2350.'.format(setpoint) }    

    ctrl.setModeSetPoint (setpoint, updateOperationFile=True)
    return { "msg" : 'Mode -> Setpoint, Target: {}'.format(setpoint) }

@app.route('/mode/profile/stop')
def webStopProfile():
    ctrl.resetToConfig()
    return { "msg" : 'Profile stopped' }

@app.route('/mode/profile/start/<name>')
def webStartProfile(name):
    if ctrl.setModeProfile(name):
        return { "msg" : 'Profile started' }
    else:
        bottle.response.status=500
        return { "msg" : 'Unknown profile, could not start' }
    
@app.route('/state')
def webState():
    return json.dumps(ctrl.getState())

@app.route('/servers')
def webServers():
    return json.dumps(config.serverlist)

@app.route('/shutdown')
def webServers():
    #If you're shutting down, then you're manually dealing, so off it first
    ctrl.setModeOff(updateOperationFile=True)
    #Let it figure out it is off
    time.sleep(2)
    #Shut the pi down
    os.system("sudo shutdown -h now")  

#Start it in daemon mode so that the web app dies when the pid loop does
threading.Thread(target=app.run, kwargs=dict(host=config.listening_ip, port=config.listening_port, quiet=True), daemon=True).start()

#Start the controller, make dang sure it is off at the end-------------------------------
ctrl.robust_run_forever()




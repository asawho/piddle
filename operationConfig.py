import os
import sys
import threading
import time
import datetime
import logging
import config
import json
import re

log = logging.getLogger('file')
smtpLog = logging.getLogger('smtp')

class OperationConfig:
    def __init__(self, path='operation.json'):
        self.configPath = path
        self.lastConfigUpdate = 0
        self.data = None

    def validateNumberSetting(self, data, name, errors, domain=None):
        if name not in data:
            errors.append("program.json has no {} setting".format(name))
        else:
            try:
                val = float(data[name])
                if domain:
                    if val < domain[0] or val > domain[1]:
                        errors.append("{} {} setting of {} is out of range {}".format(self.configPath,name,data[name], domain))        
            except:
                errors.append("{} {} setting of {} cannot be converted to a float".format(self.configPath,name,data[name]))

    def validateConfig(self, data):
        errors=[]
        valid_modes = ["OFF", "MANUAL", "SETPOINT"]

        if "mode" not in data:
            errors.append("{} has no mode setting".format(self.configPath, key))
        else:
            if data["mode"] not in valid_modes:
                errors.append("{} has an invalid mode setting of {}, must be one of {}".format(self.configPath, data["mode"], valid_modes))

        self.validateNumberSetting(data, "manualOutput", errors, (0,1))
        self.validateNumberSetting(data, "setpointTarget", errors)

        if len(errors):
            for err in errors: 
                log.error(err)
            raise Exception(errors)

    def reset(self):
        self.lastConfigUpdate = None

    def writeConfigToDisk (self):
        #print(json.dumps(self.data))
        with open(self.configPath, 'w') as outfile:
            json.dump(self.data, outfile)
        self.reset()

    def readConfigFromDisk (self):
        self.lastConfigUpdate = os.path.getmtime(self.configPath)
        with open(self.configPath) as f:  
            val = f.read()              
        self.data=json.loads(val)
        self.validateConfig(self.data)

        return self.data

    def checkForNewConfig (self):
        newt = os.path.getmtime(self.configPath)
        if self.lastConfigUpdate is None or newt > self.lastConfigUpdate:
            return self.readConfigFromDisk()
        return None

    def setModeOff(self):
        self.data["mode"]="OFF"
        self.writeConfigToDisk()

    def setModeManual(self, duty):
        self.data["mode"]="MANUAL"
        self.data["manualOutput"] = duty
        self.writeConfigToDisk()

    def setModeSetPoint(self, target):
        self.data["mode"]="SETPOINT"
        self.data["setpointTarget"] = target
        self.writeConfigToDisk()

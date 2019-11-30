import os
import sys
import threading
import time
import datetime
import logging
import config
import json
import re

def remove_comments(json_like):
    """
    Removes C-style comments from *json_like* and returns the result.  Example::
        >>> test_json = '''\
        {
            "foo": "bar", // This is a single-line comment
            "baz": "blah" /* Multi-line
            Comment */
        }'''
        >>> remove_comments('{"foo":"bar","baz":"blah",}')
        '{\n    "foo":"bar",\n    "baz":"blah"\n}'
    """
    comments_re = re.compile(
        r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
        re.DOTALL | re.MULTILINE
    )
    def replacer(match):
        s = match.group(0)
        if s[0] == '/': return ""
        return s
    return comments_re.sub(replacer, json_like)

class RuntimeConfig:
    def __init__(self, path='program.json'):
        self.log = logging.getLogger()
        self.configPath = path
        self.lastConfigUpdate = 0

    def validateProfiles(self, profiles, errors):
        #Validate the profiles
        for key, profile in profiles.items():
            if len(profile)==0:
                errors.append("Profile {} has no steps.".format(key))
            for index, value in enumerate(profile):
                if "target" not in value:
                    errors.append("Step {} of profile {} has no target set.".format(index,key))

                if "type" not in value:
                    errors.append("Step {} of profile {} has no ramp type set.".format(index,key))
                else:
                    if value["type"]!="rate" and value["type"]!="time":
                        errors.append("Step {} of profile {} has no unknown ramp type {} set.".format(index,key,value["type"]))

                if "value" not in value:
                    errors.append("Step {} of profile {} has no value set.".format(index,key))

    def validateAlerts(self, alerts, errors):
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

    def validateNumberSetting(self, data, name, errors, domain=None):
        if name not in data:
            errors.append("program.json has no {} setting".format(name))
        else:
            try:
                val = float(data[name])
                if domain:
                    if val < domain[0] or val > domain[1]:
                        errors.append("program.json {} setting of {} is out of range {}".format(name,data[name], domain))        
            except:
                errors.append("program.json {} setting of {} cannot be converted to a float".format(name,data[name]))

    def validateConfig(self, data):
        errors=[]
        valid_modes = ["OFF", "MANUAL", "SETPOINT"]

        if "mode" not in data:
            errors.append("program.json has no mode setting".format(key))
        else:
            if data["mode"] not in valid_modes:
                errors.append("program.json has an invalid mode setting of {}, must be one of {}".format(data["mode"], valid_modes))

        self.validateNumberSetting(data, "manualOutput", errors, (0,1))
        self.validateNumberSetting(data, "setpointTarget", errors)
        self.validateNumberSetting(data, "rampRatePerHour", errors)

        if "profiles" not in data:
            errors.append("program.json has no profiles settings".format(key))
        else:
            self.validateProfiles(data["profiles"], errors)

        if "alerts" in data:
            self.validateAlerts(data["alerts"], errors)

        if len(errors):
            for err in errors: 
                self.log.error(err)
            raise Exception(errors)

    def reset(self):
        self.lastConfigUpdate = None

    def readConfigFromDisk (self):
        self.lastConfigUpdate = os.path.getmtime(self.configPath)
        with open(self.configPath) as f:  
            val = f.read()              
        data=json.loads(remove_comments(val))
        self.validateConfig(data)

        return data

    def checkForNewConfig (self):
        newt = os.path.getmtime(self.configPath)
        if newt > self.lastConfigUpdate:
            return self.readConfigFromDisk()
        return None
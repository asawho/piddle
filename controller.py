from enum import Enum
import os
import sys
import threading
import time
import datetime
import sched
import logging
import json
import config
import sensors
import runtimeConfig
import config
from simple_pid import PID

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

log = logging.getLogger()

class RampStep:
    def __init__(self, currentValue, targetValue, rampType, typeValue):
        self.rampStartTime = time.time()
        self.rampStartPoint = currentValue

        #In degrees per hour
        if rampType=="rate":
            self.rampEndTime = self.rampStartTime + (abs(targetValue - currentValue)/typeValue)*3600
        #In hours
        elif rampType=="time":
            self.rampEndTime = self.rampStartTime + typeValue*3600
        else:
            raise Exception("Unknown or missing ramp type {}".format(rampType))

        self.rampPointDelta = targetValue - currentValue
        self.rampDuration = self.rampEndTime-self.rampStartTime
        self.rampEndPoint = targetValue    

        dtstr = datetime.datetime.fromtimestamp(self.rampEndTime).strftime("%c")
        log.info('Ramping -> Current: {} Target: {} Type: {} Value: {} EndTime: {}'.format(currentValue, targetValue, rampType, typeValue, dtstr))

    def isComplete(self):
        return time.time() >= self.rampEndTime

    def finalTarget(self):
        return self.rampEndPoint

    def finalTime(self):
        return self.rampEndTime

    def currentTarget(self):
        val = self.rampStartPoint + self.rampPointDelta * ((time.time()-self.rampStartTime)/self.rampDuration)
        if self.rampEndPoint > self.rampStartPoint:
            val = min(val,self.rampEndPoint)
        if self.rampEndPoint < self.rampStartPoint:
            val = max(val,self.rampEndPoint)
        return (val)

class ControllerMode(Enum):
    OFF = 1
    MANUAL = 2
    SETPOINT = 3
    PROFILE = 4

class PidController(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        self.lock = threading.Lock()

        self.time_step = config.sensor_time_wait
        self.tc = sensors.TempSensor()

        self.hotpins = config.gpio_heat
        if not isinstance(config.gpio_heat, list):
            self.hotpins = [config.gpio_heat]
        for val in self.hotpins:
            GPIO.setup(val, GPIO.OUT)
            self.pinOff(val)
        self.dutyCycle=0.0
        self.sc = sched.scheduler(timefunc=time.time)

        self.runtimeConfig = runtimeConfig.RuntimeConfig()
        self.cfgData = None

        self.pid = PID (config.pid_kp, config.pid_ki, config.pid_kd, auto_mode=True, sample_time=None, output_limits=(0.0,1.0))
        self.mode = ControllerMode.OFF

        self.modeManual_Output = 0

        self.modeSetPoint_Target = 0
        self.modeSetPoint_RampRatePerHour = 0

        self.modeProfile_Profile = None
        self.modeProfile_Step = 0

        self.ramping = False
        self.ramp = None

    def resetToConfig(self):
        self.runtimeConfig.reset()

    def enableAlerts(self):
        for x in range(1,5):
            self.tc.clearAlert(x)
        if "alerts" in self.cfgData:
            for a in self.cfgData["alerts"]:
                self.tc.setAlert(target=a["target"], latching=a["latching"], activeLogicLevel=a["activeLogicLevel"], alertOutputPin=a["alertOutput"])

    def mechanicalRelayOff(self):
        #Falsely trigger the temperature alert to turn off the mechanical relay
        self.tc.clearAlert(1)
        self.tc.setAlert(target=-30, latching=False, activeLogicLevel=1, alertOutputPin=1)

    def setModeOff(self):
        log.info('Mode -> Off')
        with self.lock:
            self.mode = ControllerMode.OFF
            self.dutyCycle=0
            for val in self.hotpins:
                GPIO.setup(val, GPIO.OUT)
                self.pinOff(val)
            self.mechanicalRelayOff()

        return True

    def setModeManual(self, duty):
        log.info('Mode -> Manual, Output: {}'.format(duty))
        with self.lock:
            self.mode = ControllerMode.MANUAL
            self.modeManual_Output = duty
            self.dutyCycle=duty
            self.enableAlerts()
        return True

    def setModeSetPoint(self, target, rampRatePerHour=0):
        log.info('Mode -> SetPoint, Target: {} RampRatePerHour: {}'.format(target, rampRatePerHour))
        with self.lock:
            self.mode = ControllerMode.SETPOINT
            self.modeSetPoint_Target = target
            self.modeSetPoint_RampRate = rampRatePerHour
            if rampRatePerHour > 0:
                self.ramping = True
                self.ramp = RampStep (self.tc.temperature, target, "rate", rampRatePerHour)
            self.enableAlerts()
        return True

    def setModeProfile(self, profilename):
        if profilename not in self.cfgData["profiles"]:
            self.log.error('Could not start profile {} it is not defined in program.json'.format(name))
            return False
        profile = self.cfgData["profiles"][profilename]

        log.info('Mode -> Profile: {}'.format(profilename))
        with self.lock:
            self.mode = ControllerMode.PROFILE
            self.modeProfile_Name = profilename
            self.modeProfile_Profile = profile
            self.modeProfile_Step = 0
            self.ramping = True
            self.ramp = RampStep (self.tc.temperature, self.modeProfile_Profile[self.modeProfile_Step]["target"], self.modeProfile_Profile[self.modeProfile_Step]["type"], self.modeProfile_Profile[self.modeProfile_Step]["value"])
            self.enableAlerts()
        return True

    def getState(self, shortNames=False):
        data = {}
        short = {}
        data["mode"] = short["m"] = str(self.mode)
        data["currentTemperature"] = short["curr"] = round(self.tc.temperature)
        data["currentTarget"] = short["ctgt"] = round(self.pid.setpoint)
        data["ramping"] = short["ramping"] = self.ramping
        data["rmpftgt"] = short["rmpftgt"] = round(self.ramp.finalTarget()) if self.ramping else 0
        data["rmpftime"]= short["rmpftime"] = datetime.datetime.fromtimestamp(self.ramp.finalTime()).strftime("%H:%M:%S") if self.ramping else 0
        data["output"] = short["out"] = round(self.dutyCycle, 2)
        data["pp"], data["pi"], data["pd"] = round(self.pid.components[0],3), round(self.pid.components[1],3), round(self.pid.components[2],3)
        short["pp"], short["pi"], short["pd"] = round(self.pid.components[0],3), round(self.pid.components[1],3), round(self.pid.components[2],3)
        return(short if shortNames else data)

    #What this essentially does it takes the duty cycle and it flips the SSR on/off
    #every 1/60 of a second at the minimum sized chunks that can be fit in the the 
    #time_step.  It just does all this before hand and then sets these up as a 
    #schedule to be run.  Since the scheduled events are lined up for the entire
    #time_step, then when sc.run() is done, we are ready for another regular loop.    
    def pinOn(self, pinNumber):
        #print("{}:1 ".format(pinNumber), end='')
        #print("1".format(pinNumber), end='')
        GPIO.output(pinNumber, 1)

    def pinOff(self, pinNumber):
        #print("{}:0 ".format(pinNumber), end='')
        #print("0".format(pinNumber), end='')
        GPIO.output(pinNumber, 0)

    def applyOutput(self, syncStartTime, carryInTime, duty):
        flips = self.time_step*60
        #print()
        #print()
        #print("On:{} Off:{} Ratio:{} Carry: {}".format(numberOn, numberOff, oneOnForEveryHowManyOff, carryInTime))
        runningTotal = carryInTime
        self.hotpins=self.hotpins[-1:] + self.hotpins[:-1]
        numPins=len(self.hotpins)
        for step in range(flips):
            runningTotal+=duty
            for i in range(numPins):
                if runningTotal >= 1.0/numPins:
                    runningTotal -= 1.0/numPins
                    self.sc.enterabs(syncStartTime+step/flips, i+1, self.pinOn, (self.hotpins[i],))
                else:                    
                    self.sc.enterabs(syncStartTime+step/flips, i+1, self.pinOff, (self.hotpins[i],))
        carryOverTime = runningTotal
        self.sc.run()
        #print("")
        return carryOverTime

    def checkConfig(self):
        #Read any new configuration settings
        data = self.runtimeConfig.checkForNewConfig()
        if not data: 
            return
        log.info('Configuration file program.json updated.')

        self.cfgData = data

        if data["mode"]=="OFF":
            self.setModeOff()
        if data["mode"]=="MANUAL":
            self.setModeManual(data["manualOutput"])
        if data["mode"]=="SETPOINT":
            self.setModeSetPoint(data["setpointTarget"], data["rampRatePerHour"])

    def run_forever(self):
        #Start the synchro timer, try and make it an even second to start
        syncStartTime = int(time.time()) + self.time_step
        carryOverTime = 0
        time.sleep(syncStartTime-time.time())
        lastLogTime=0

        while True:
            #Read my new thermocouple value, IMPORTANT ,this should take less than 1/60 of a second
            #if we are going for bursting hotpins.  MCP9600 takes ~4ms
            self.tc.update()

            #Read any new configuration settings
            self.checkConfig()

            #Don't let anyone update my internals while I am handling my tick, once I am done
            #and sleeping, change my state all you want
            with self.lock:
                #MANUAL and OFF don't do anything here
                if self.mode == ControllerMode.SETPOINT:
                    self.pid.setpoint = self.modeSetPoint_Target
                    if self.ramping:
                        if not self.ramp.isComplete():
                            self.pid.setpoint = self.ramp.currentTarget()
                        else:
                            self.ramping=False
                            self.ramp=None
                    self.dutyCycle = self.pid(self.tc.temperature)

                if self.mode == ControllerMode.PROFILE:
                    self.pid.setpoint = self.modeProfile_Profile[-1]["target"]
                    if self.ramping:
                        if not self.ramp.isComplete():
                            self.pid.setpoint = self.ramp.currentTarget()
                        else:
                            self.modeProfile_Step=self.modeProfile_Step+1
                            if self.modeProfile_Step<len(self.modeProfile_Profile):
                                self.ramp = RampStep (self.tc.temperature, self.modeProfile_Profile[self.modeProfile_Step]["target"], self.modeProfile_Profile[self.modeProfile_Step]["type"], self.modeProfile_Profile[self.modeProfile_Step]["value"])
                                self.pid.setpoint = self.ramp.currentTarget()
                            else:
                                self.ramping=False
                                self.ramp=None
                    self.dutyCycle = self.pid(self.tc.temperature)

            #Handle the hotpins, do this outside of the lock as this really is constant work,
            carryOverTime = self.applyOutput(syncStartTime, carryOverTime, self.dutyCycle)

            #Log it
            #print(json.dumps(self.getState(True)))
            if self.mode!= ControllerMode.OFF and time.time() - lastLogTime > config.log_frequency:
                lastLogTime=time.time()
                log.info(json.dumps(self.getState(True)))

            #The loop uses syncStartTime rather than adding to the current time as there
            #would be a small drift that way.  This may be something that would actually be
            #a benefit if we find a sort of unreliable timing zone where the SSR is being
            #flipped right on the edge of the AC sine wave which could lead to flip flopping
            #odd behavior.
            syncStartTime += self.time_step

from enum import Enum
import os
import sys
import threading
import time
import datetime
import sched
import logging
import config
import sensors
import runtimeConfig
import config
from simple_pid import PID

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

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

        self.rampDuration = self.rampEndTime-self.rampStartTime
        self.rampEndPoint = targetValue    

    def isComplete(self):
        return time.time() >= self.rampEndTime

    def finalTarget(self):
        return self.rampEndPoint

    def finalTime(self):
        return self.rampEndTime

    def currentTarget(self):
        val = self.rampStartPoint + (time.time()-self.rampStartTime)/self.rampDuration
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

        self.hotpin = config.gpio_heat
        GPIO.setup(self.hotpin, GPIO.OUT)
        self.dutyCycle=0.0
        self.pinOff()
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

    def setModeOff(self):
        with self.lock:
            self.mode = ControllerMode.OFF
            self.dutyCycle=0
            self.pinOff()
        return True

    def setModeManual(self, duty):
        with self.lock:
            self.mode = ControllerMode.MANUAL
            self.modeManual_Output = duty
            self.dutyCycle=duty
        return True

    def setModeSetPoint(self, target, rampRatePerHour=0):
        with self.lock:
            self.mode = ControllerMode.SETPOINT
            self.modeSetPoint_Target = target
            self.modeSetPoint_RampRate = rampRatePerHour
            if rampRatePerHour > 0:
                self.ramping = True
                self.ramp = RampStep (self.tc.temperature, target, "rate", rampRatePerHour)
        return True

    def setModeProfile(self, profilename):
        if profilename not in self.cfgData["profiles"]:
            self.log.error('Could not start profile {} it is not defined in program.json'.format(name))
            return False
        profile = self.cfgData["profiles"][profilename]

        with self.lock:
            self.mode = ControllerMode.PROFILE
            self.modeProfile_Name = profilename
            self.modeProfile_Profile = profile
            self.modeProfile_Step = 0
            self.ramping = True
            self.ramp = RampStep (self.tc.temperature, self.modeProfile_Profile[self.modeProfile_Step]["target"], self.modeProfile_Profile[self.modeProfile_Step]["type"], self.modeProfile_Profile[self.modeProfile_Step]["value"])
        
        return True

    def getState(self):
        data = {}
        data["mode"] = str(self.mode)
        data["temperature"] = self.tc.temperature
        if self.mode == ControllerMode.MANUAL:
            data["manualOutput"] = self.modeManual_Output
        if self.mode == ControllerMode.SETPOINT:
            data["target"] = self.modeSetPoint_Target
            data["rampRate"] = self.modeSetPoint_RampRate
        if self.mode == ControllerMode.PROFILE:
            data["profile"] = self.modeProfile_Name
            data["profileStep"] = self.modeProfile_Step
            if self.ramping:
                data["target"] = self.ramp.finalTarget()
                data["targetTime"]= self.ramp.finalTime()
                data["profileComplete"]=False
            else:
                data["target"] = self.modeProfile_Profile[-1]["target"]
                data["targetTime"]=time.time()
                data["profileComplete"]=self.ramp.isComplete()                

        return data

    #What this essentially does it takes the duty cycle and it flips the SSR on/off
    #every 1/60 of a second at the minimum sized chunks that can be fit in the the 
    #time_step.  It just does all this before hand and then sets these up as a 
    #schedule to be run.  Since the scheduled events are lined up for the entire
    #time_step, then when sc.run() is done, we are ready for another regular loop.    
    def pinOn(self):
        #print("On  ", end='')
        GPIO.output(self.hotpin, 1)

    def pinOff(self):
        #print("Off ", end='')
        GPIO.output(self.hotpin, 0)

    def applyOutput(self, syncStartTime, carryInTime, duty):
        flips = self.time_step*60
        numberOn = flips * duty
        numberOff = flips - numberOn
        oneOnForEveryHowManyOff = (numberOn/numberOff) if numberOff > 0 else 10000000
        #print("On:{} Off:{} Ratio:{} Carry: {}".format(numberOn, numberOff, oneOnForEveryHowManyOff, carryInTime))
        runningTotal = carryInTime
        for step in range(flips):
            if runningTotal >= 1:
                runningTotal -= 1.0
                self.sc.enterabs(syncStartTime+step/flips, 1, self.pinOn)
            else:                    
                runningTotal += oneOnForEveryHowManyOff
                self.sc.enterabs(syncStartTime+step/flips, 1, self.pinOff)
        carryOverTime = runningTotal
        self.sc.run()
        #print("")
        return carryOverTime

    def checkConfig(self):
        #Read any new configuration settings
        data = self.runtimeConfig.checkForNewConfig()
        if not data: 
            return

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

            #The loop uses syncStartTime rather than adding to the current time as there
            #would be a small drift that way.  This may be something that would actually be
            #a benefit if we find a sort of unreliable timing zone where the SSR is being
            #flipped right on the edge of the AC sine wave which could lead to flip flopping
            #odd behavior.
            syncStartTime += self.time_step

from enum import Enum
import os, signal, sys
import threading
import time
import datetime
import sched
import logging
import json
import config
import sensors
import operationConfig
import config
from simple_pid import PID

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

log = logging.getLogger('file')
smtpLog = logging.getLogger('smtp')

class RampStep:
    def __init__(self, startValue, targetValue, rampType, typeValue):
        self.rampStartTime = time.time()
        self.rampStartPoint = startValue

        #In degrees per hour
        if rampType=="rate":
            self.rampEndTime = self.rampStartTime + (abs(targetValue - startValue)/typeValue)*3600
        #In hours
        elif rampType=="time":
            self.rampEndTime = self.rampStartTime + typeValue*3600
        else:
            raise Exception("Unknown or missing ramp type {}".format(rampType))

        self.rampPointDelta = targetValue - startValue
        self.rampDuration = self.rampEndTime-self.rampStartTime
        self.rampEndPoint = targetValue    

        dtstr = datetime.datetime.fromtimestamp(self.rampEndTime).strftime("%c")
        log.info('Ramping -> Current: {} Target: {} Type: {} Value: {} EndTime: {}'.format(startValue, targetValue, rampType, typeValue, dtstr))

    def isComplete(self):
        return time.time() >= self.rampEndTime

    def finalTarget(self):
        return self.rampEndPoint

    def finalTime(self):
        return self.rampEndTime

    def currentTarget(self):
        if self.rampDuration==0:
            val = self.rampEndPoint
        else:
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

        self.terminateSignalReceived = False

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

        self.operationConfig = operationConfig.OperationConfig()

        self.pid = PID (config.pid_kp, config.pid_ki, config.pid_kd, auto_mode=True, sample_time=None, output_limits=(0.0,1.0))
        self.mode = ControllerMode.OFF

        self.modeManual_Output = 0

        self.modeSetPoint_Target = 0
        self.modeSetPoint_RampRatePerHour = 0

        self.modeProfile_Profile = None
        self.modeProfile_Step = 0

        self.ramping = False
        self.ramp = None

        self.openLoopStarted = False
        self.openLoopStartTemperature = None
        self.openLoopStartTime = None

        self.alertNoted=[False]*len(config.alerts)

    def resetToConfig(self):
        self.operationConfig.reset()

    def enableAlerts(self):
        self.alertNoted=[False]*len(config.alerts)
        for x in range(1,5):
            self.tc.clearAlert(x)
        for a in config.alerts:
            self.tc.setAlert(target=a["target"], latching=a["latching"], activeLogicLevel=a["activeLogicLevel"], alertOutputPin=a["alertOutput"])

    def mechanicalRelayOff(self):
        #Falsely trigger the temperature alert to turn off the mechanical relay
        self.tc.clearAlert(1)
        self.tc.setAlert(target=-30, latching=False, activeLogicLevel=1, alertOutputPin=1)

    def setModeOff(self, updateOperationFile=False):
        # Write the change to disk and let the refresh handle it
        if updateOperationFile:
            self.operationConfig.setModeOff()
            return

        log.info('Mode -> Off')
        with self.lock:
            self.mode = ControllerMode.OFF
            self.dutyCycle=0
            for val in self.hotpins:
                GPIO.setup(val, GPIO.OUT)
                self.pinOff(val)
            self.mechanicalRelayOff()
            #Reset my kp, ki, kd
            self.pid.reset()

        return True

    def setModeManual(self, duty, updateOperationFile=False):
        # Write the change to disk and let the refresh handle it
        if updateOperationFile:
            self.operationConfig.setModeManual(duty)
            return

        log.info('Mode -> Manual, Output: {}'.format(duty))
        with self.lock:
            self.mode = ControllerMode.MANUAL
            self.modeManual_Output = duty
            self.dutyCycle=duty
            self.enableAlerts()
        return True

    def setModeSetPoint(self, target, rampRatePerHour=None, updateOperationFile=False):
        # Write the change to disk and let the refresh handle it
        if updateOperationFile:
            self.operationConfig.setModeSetPoint(target)
            return

        log.info('Mode -> SetPoint, Target: {} RampRatePerHour: {}'.format(target, rampRatePerHour))
        with self.lock:
            self.mode = ControllerMode.SETPOINT
            self.modeSetPoint_Target = target
            self.modeSetPoint_RampRate = config.rampRatePerHour if rampRatePerHour is None else rampRatePerHour
            if self.modeSetPoint_RampRate > 0:
                self.ramping = True
                self.ramp = RampStep (self.tc.temperature, target, "rate", self.modeSetPoint_RampRate)
            self.enableAlerts()
        return True

    def setModeProfile(self, profilename):
        #print(profilename, config.profiles)
        if profilename not in config.profiles:
            return False
        profile = config.profiles[profilename]

        log.info('Mode -> Profile: {}'.format(profilename))
        with self.lock:
            self.mode = ControllerMode.PROFILE
            self.modeProfile_Name = profilename
            self.modeProfile_Profile = profile
            self.modeProfile_Step = 0
            self.ramping=False
            self.ramp=None
            if self.modeProfile_Profile[self.modeProfile_Step]["type"] != "mode":
                self.ramping = True
                self.ramp = RampStep (self.tc.temperature, self.modeProfile_Profile[self.modeProfile_Step]["target"], self.modeProfile_Profile[self.modeProfile_Step]["type"], self.modeProfile_Profile[self.modeProfile_Step]["value"])
                self.enableAlerts()

        return True

    def getState(self, shortNames=False):
        data = {}
        short = {}
        #Strip out the 'ControllerMode.' from the string
        data["mode"] = short["m"] = str(self.mode)[str(self.mode).index('.')+1:]
        data["currentTemperature"] = short["curr"] = round(self.tc.temperature)
        data["currentColdTemperature"] = short["cold"] = round(self.tc.coldJunction)
        data["currentTarget"] = short["ctgt"] = round(self.pid.setpoint)
        data["currentOutput"] = short["out"] = round(self.dutyCycle, 2)
        data["ramping"] = short["ramping"] = self.ramping
        data["rampTarget"] = short["rmptgt"] = round(self.ramp.finalTarget()) if self.ramping else 0
        data["rampTime"]= short["rmptime"] = datetime.datetime.fromtimestamp(self.ramp.finalTime()).strftime("%H:%M:%S") if self.ramping else 0
        data["profileStep"] = short["profile"] = self.modeProfile_Step if self.mode==ControllerMode.PROFILE else ''
        data["profileName"] = short["profile"] = self.modeProfile_Name if self.mode==ControllerMode.PROFILE else ''

        data["cfgManualOutput"] = short["cfgout"] = self.operationConfig.data["manualOutput"] if self.operationConfig.data is not None else 0        
        data["cfgSetpoint"] = short["cfgsetpt"] = self.operationConfig.data["setpointTarget"] if self.operationConfig.data is not None else 0        
        data["cfgProfiles"] = short["cfgprofiles"] = config.profiles

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
        data = self.operationConfig.checkForNewConfig()
        if not data: 
            return
        log.info('Configuration file updated.')

        if data["mode"]=="OFF":
            self.setModeOff()
        if data["mode"]=="MANUAL":
            self.setModeManual(data["manualOutput"])
        if data["mode"]=="SETPOINT":
            self.setModeSetPoint(data["setpointTarget"], config.rampRatePerHour)

    def _sigDown(self, signum, frame):
        log.info('Signal Terminated')
        self.terminateSignalReceived=True

    def robust_run_forever(self):
        # So it turns out that when you don't handle SIGTERM, you just get shutdown, no finally
        # For the Daemon operation, it is absolutely critical we handle SIGTERM and shutdown
        # all outputs.
        signal.signal(signal.SIGINT, self._sigDown)
        signal.signal(signal.SIGTERM, self._sigDown)
        try:
            self._run_forever()
        except Exception as e:
            log.error("Shutting Down -> Unhandled Exception: " + str(e))
            smtpLog.error("Shutting Down -> Unhandled Exception: " + str(e))
        finally:
            self.setModeOff()

    def _run_forever(self):
        #Start the synchro timer, try and make it an even second to start
        syncStartTime = int(time.time()) + self.time_step
        carryOverTime = 0
        time.sleep(syncStartTime-time.time())
        lastLogTime=0

        while not self.terminateSignalReceived:
            #Read my new thermocouple value, IMPORTANT ,this should take less than 1/60 of a second
            #if we are going for bursting hotpins.  MCP9600 takes ~4ms
            self.tc.update()

            #Read any new configuration settings
            self.checkConfig()

            # Don't let anyone update my internals while I am handling my tick, once I am done,
            # change my state all you want
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
                    #If I am ramping, then I am engaged in whatever step I am in
                    if self.ramping:
                        self.pid.setpoint = self.ramp.currentTarget()
                        #If I have finished ramping, then transition to the next step
                        if self.ramp.isComplete():
                            self.ramping=False
                            self.ramp=None
                            self.modeProfile_Step=self.modeProfile_Step+1
                            if self.modeProfile_Step < len(self.modeProfile_Profile):
                                #If that step is not of type mode, then it is a ramp
                                if self.modeProfile_Profile[self.modeProfile_Step]["type"]!="mode":
                                    #Set the start value to the prior ramp steps target value, this prevents a lagging oven from starting ramps from the wrong temperature
                                    self.ramp = RampStep (self.modeProfile_Profile[self.modeProfile_Step-1]["target"], self.modeProfile_Profile[self.modeProfile_Step]["target"], self.modeProfile_Profile[self.modeProfile_Step]["type"], self.modeProfile_Profile[self.modeProfile_Step]["value"])
                                    self.ramping=True
                                    self.pid.setpoint = self.ramp.currentTarget()                                    
                    self.dutyCycle = self.pid(self.tc.temperature)

            #Outside of the lock, check for mode transitions and game over, do these to the disk so they
            if self.mode == ControllerMode.PROFILE:
                #If I made it to the end, then there was no transition, so turn it off
                if self.modeProfile_Step >= len(self.modeProfile_Profile):
                    self.setModeOff(updateOperationFile=True)

                #If I am not at the end and I am on a transition step, then transition
                elif self.modeProfile_Profile[self.modeProfile_Step]["type"]=="mode":
                    md = self.modeProfile_Profile[self.modeProfile_Step]["value"]
                    if md=="off":
                        self.setModeOff(updateOperationFile=True)
                    elif md == "manual":
                        self.setModeManual(self.modeProfile_Profile[self.modeProfile_Step]["target"], updateOperationFile=True)
                    elif md == "setpoint":
                        self.setModeSetPoint(self.modeProfile_Profile[self.modeProfile_Step]["target"], updateOperationFile=True)
                    elif md=="profile":
                        profname = self.modeProfile_Profile[self.modeProfile_Step]["target"]
                        if not self.setModeProfile(profname):
                            msg = "Attempt to transition to unknown profile {}. Shutting down.".format(profname)
                            log.error(msg)
                            smtpLog.error(msg)
                            self.setModeOff(updateOperationFile=True)
                    else:
                        msg = "Unknown profile mode transition type {}".format(md)
                        log.error(msg)
                        smtpLog.error(msg)
                        self.setModeOff(updateOperationFile=True)

            #Check for openLoop conditions
            if config.openLoop_monitor_enabled:
                if self.mode != ControllerMode.OFF and self.mode != ControllerMode.MANUAL:
                    #If we are not at 100% power, then we are not running away
                    if self.dutyCycle >= 1.0:
                        #Start monitoring
                        if not self.openLoopStarted:
                            self.openLoopStarted = True
                            self.openLoopStartTemperature = self.tc.temperature
                            self.openLoopStartTime = time.time() 
                        #Continue monitoring
                        else:
                            #If we are past our monitor window, verify we are not lagging
                            if time.time() > self.openLoopStartTime + config.openLoop_time_window:
                                #We must have an open loop
                                if (self.tc.temperature - self.openLoopStartTemperature) < config.openLoop_minimum_temperature_change:
                                    msg = 'Open Loop condition met, start: {}F end: {}F over: {}seconds at 100% power. Shutting down.'.format(self.openLoopStartTemperature, self.tc.temperature, config.openLoop_time_window)
                                    log.error(msg)
                                    smtpLog.error(msg)
                                    self.setModeOff(updateOperationFile=True)
                                #Well we made it past based on the temperature delta, but keep sliding that window going
                                else:
                                    self.openLoopStartTemperature = self.tc.temperature
                                    self.openLoopStartTime = time.time() 

                    #Flip back to no open loop needed for now
                    else:                        
                        self.openLoopStarted = False

            # Check for temperature exceeded, so run through all of the alerts.  NOTE the MCP9600 has hardware
            # pins that also do this alert.  Those hardware pins control the relay.  I mean really if you're over
            # temperature, the duty cycle should already be zero.  So, meh how valuable I don't know.  But...
            # the email and log alerts are definitely valuable.  Have to know it is tripped.
            for x in range(len(config.alerts)):
                #If we are over, then we have a problem and set the dutyCyle to zero
                if self.tc.temperature > config.alerts[x]["target"]:
                    self.dutyCycle = 0
                    #Send out the email
                    if not self.alertNoted[x]:
                        msg = "Temperature Limit Exceeded -> Limit {} < Actual {}".format(config.alerts[x]["target"], self.tc.temperature)
                        log.error(msg)
                        smtpLog.error(msg)              
                        self.alertNoted[x] = True                    
                        #If it is a latching alert, then it requires manual intervention, so go to off
                        if config.alerts[x]["latching"]:
                            self.setModeOff(updateOperationFile=True)

                #Else if there was a prior problem, continue at zero
                elif self.alertNoted[x]:
                    self.dutyCycle=0
                    #If it is  not latching and we have come back under by 5, re-enable
                    if not config.alerts[x]["latching"] and self.tc.temperature < config.alerts[x]["target"] - 5:                        
                        self.alertNoted[x]=False

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

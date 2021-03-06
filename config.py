import os
hostname = os.uname()[1].lower()

### Default Configuration Values for All Instances----------------------------------------------------------
#
#   This file has just the configuration values.  The operational values are found in operation.json.  
#   When updating this files values, you must restart the piddle service for them to take effect.  This is
#   in contrast to the operation settings which can be updated in the file and take effect immediately.
#
#   Documentation on Operational Settings
#   For OFF, MANUAL and SETPOINT mode, piddle will resume operation on boot.  If in SETPOINT mode,
#   and the temperature has deviated from the SETPOINT, piddle will ramp to the setpoint at the
#   rate specified.
#
#   Running a profile is not done in the operational file.  Profiles are initiated from the command
#   line/rest endpoint.  This is to avoid confusion with reboots and whether the profile was 
#   running/should be running.  TODO --> Profiles can be resumed on a restart, which will be a 
#   flag to the command to run them.
# --------------------------------------------------------------------------------------------------------

#  Logging frequency in seconds
log_frequency = 30

# Server
listening_ip = "0.0.0.0"
listening_port = 8080

# Main loop duration in seconds
sensor_time_wait = 1

#   PID parameters
pid_kp = 0.02          # Proportional
pid_ki = 0.00025       # Integration
pid_kd = 0.0           # Derivative

pid_output_max = 1.0   # 0 to max for % output

### Outputs BCM, Switches zero-cross solid-state-relay, this is either a single pin
# or an array of pins.  For n pins, the assumption is each pin controls 1/n percent
# of the total power.  So for two pins, each pin would control 50% of the power.  
# Power is automatically distributed between the pins so no one element is disproportionately
# loaded.
#
# The primary purpose in having multiple pins is to be able to "feather" the power
# and avoid flickering lights for high current devices.
#
# If this list is empty, this device is considered a monitor and nothing will be controlled.
# You do need it to still be an empty list if there are none, so = []
gpio_heat = [23]

#Thermocouple type 
thermocouple_type = 'K'

#Minimum filtering on the chip
mcp9600_filter_coefficient = 0b001

#How many seconds of failed thermocouple reads before raising an exception
bad_thermocouple_read_timeout = 60

### Monitor for openLoop conditions
# The controller can monitor for openLoop conditions where full power is applied and yet the 
# temperature is not changing by some rate.  You can define whether this is enabled or not
# and what the minimum temperature increase is over a certain time (in seconds) when power
# is at 100%.  NOTE: This is monitor can only be tripped if both are true, power output = 100%
# for the openLoop_time_window and the temperature changes by less than openLoop_minimum_temperature_change
openLoop_monitor_enabled = True
openLoop_time_window = 60
openLoop_minimum_temperature_change = 5

#SETPOINT AND PROFILE: When ramping to a setpoint or to resume a profile after a 
#power cycle, what is the rate to ramp at.  If ==0, then as fast as possible
rampRatePerHour : 0

#What alerts do I have, the default one keeps us under 212F
# { target: [target temperature], latching: [True or False], activeLogicLevel: [0 or 1], alertOutput: [1 through 5] }
alerts= [
    #Non-latching
    #{ target: 2300, latching: False, activeLogicLevel: 1, alertOutput: 1 }
    #Latching
    { "target": 212, "latching": True, "activeLogicLevel": 0, "alertOutput": 1 }
]

# These profiles are shared between all networked temperature controllers, so there is no need for duplication if
# multiple controllers share the same profiles.
#
# What profiles do I know, of the format 
#  "name" : [steps]
# Where each step is of the format
#  { "target": temperature, "type": 'rate' or 'time' or 'mode', "value": value for the type }
# So for example, the following will ramp to 1000F at a rate of 100F per hour
#  { "target": 1000, "type": 'rate', "value": 100 }
# Another example, the following will ramp to 1000F in one hour
#  { "target": 1000, "type": 'time', "value": 1 }
# Another example, the following will transition to setpoint mode targeting 1000 (this will update operation.json)
#  { "target": 1000, "type": 'mode', "value": 'setpoint' }
# Another example, the following will transition to manual mode with 0.5 output power (this will update operation.json)
#  { "target": 0.5, "type": 'mode', "value": 'manual' }
# Another example, the following will transition to the 'anneal' profile
#  { "target": 'anneal', "type": 'mode', "value": 'profile' }
# Another example, the following will transition to off
#  { "type": 'mode', "value": 'off' }
profiles= { 
    "test" : [
        #Ramp to 50
        { "target": 40, "type": "rate", "value": 2000 },
        #Hold for one minute
        { "target": 40, "type": "time", "value": 1/360 },
        #Ramp to 75
        { "target": 42, "type": "rate", "value": 2000 },
        #Back to room
        { "target": 40, "type": "time", "value": 0 }
    ],
    "castable-dryout" : [
        #Ramp to 200
        { "target": 200, "type": "rate", "value": 50 },
        #Hold for 5 hours
        { "target": 200, "type": "time", "value": 5 },
        #Ramp to 1000 at 50
        { "target": 1000, "type": "rate", "value": 50 },
        #Back to room
        { "target": 50, "type": "time", "value": 0.5 }
    ]
}    

### --------------------------------------------------------------------------------------------------------
# List of servers on this network that will take part in watchdog and be displayed in the web interface
# It is not necessary to have any servers in this list.
serverlist=['furnace','annealer','warmer','canepull']
if hostname not in serverlist:
    serverlist.append(hostname)

### Configuration Values for Specific Instances-------------------------------------------------------------
### --------------------------------------------------------------------------------------------------------

if hostname=="warmer":
    #Ramp to operating in 0.5 hours
    rampRatePerHour=2000
    #Over 1100F and we are in trouble
    alerts = [
        { "target": 1100, "latching": True, "activeLogicLevel": 0, "alertOutput": 1 }
    ]

if hostname=="canepull":
    pid_kp = 0.005         # Proportional
    pid_ki = 0.00001       # Integration
    pid_kd = 0.0           # Derivative

    pid_output_max = 0.4   # Max 

    #Ramp to operating in 1 hour
    rampRatePerHour=1000
    #Over 2000F and we are in trouble
    alerts = [
        { "target": 2000, "latching": True, "activeLogicLevel": 0, "alertOutput": 1 }
    ]
    profiles.update({ 
        "warmy" : [
            { "target": 400, "type": "time", "value": 5 },
            { "target": 400, "type": "mode", "value": 'setpoint' }
        ],
        "cook" : [
            #Needed to avoid a 1 hour ramp to 1000 if we are not exactly 1000
            { "target": 1700, "type": "time", "value": 0 },
            #Hold at 1000 for an hour
            { "target": 1700, "type": "time", "value": 2 },
            #Transition to 1700 and hold
            { "target": 1700, "type": 'mode', "value": 'setpoint' }
        ]
    })    

if hostname=="annealer":
    #Ramp to operating in 1 hour
    rampRatePerHour = 1000
    alerts= [
        { "target": 1100, "latching": True, "activeLogicLevel": 0, "alertOutput": 1 }
    ]
    profiles.update({ 
        "anneal" : [
            #Needed to avoid a 1 hour ramp to 1000 if we are not exactly 1000
            { "target": 1000, "type": "time", "value": 0 },
            #Hold at 1000 for an hour
            { "target": 1000, "type": "time", "value": 1 },
            #Drop to 900 over an hour
            { "target": 900, "type": "time", "value": 1 },
            #Drop to room temperature over 6
            { "target": 70, "type": "time", "value": 6 }
        ]
    })

if hostname=="furnace":
    pid_kp = 0.01          # Proportional
    pid_ki = 0.00001       # Integration
    pid_kd = 0.0           # Derivative

    gpio_heat = [23,24]
    thermocouple_type = 'S'
    mcp9600_filter_coefficient = 0b111
    rampRatePerHour = 150
    alerts= [
        { "target": 2350, "latching": True, "activeLogicLevel": 0, "alertOutput": 1 }
    ]
    profiles.update({ 
        "cook" : [
            #Ramp to cooking temperature over 1 hour
            { "target": 2250, "type": "time", "value": 1 },
            #Cook for 4 hours
            { "target": 2250, "type": "time", "value": 4 },
            #Set Fine setpoint
            { "target": 1900, "type": "time", "value": 0 },
            #Drop and hold for a total of 4 hours
            { "target": 1900, "type": "time", "value": 4 },
            #Back to working
            { "target": 2050, "type": "time", "value": 1 }
        ]
    })



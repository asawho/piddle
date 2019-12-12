## Piddle - A Python Raspberry PI Based Temperature Controller Using an MCP9600 
This project is a python, raspberry pi, mcp9600 based temperature controller.  It provides the temperature controller as a daemon. Optionally, you can enable a web interface and api that allows you to monitor and control the operation through a browser.  Optionally multiple temperature controllers can be setup to monitor each other on the same network, providing watchdog capacity.  When multiple controllers are setup, the web interface can aggregate all of the controllers on one display.  The application can also just be a temperature monitor without any controller output configured.

TODO - do the run away broken sensor checks
TODO - do the watchdog

### Wiring and Hardware
TODO 

### Installing 
```
git clone https://github.com/asawho/piddle
```
### Configuration
All configuration is done in config.py.  The comments for settings are in the file.  Temperature is assumed to be in farenheit.  
```
nano config.py
```

### Operation
This project has been designed to mimic the functionality of standalone temperature controllers.  So, its current operation is written to disk and configured from the file operation.json.  Within this file there are 3 settings,
```
{"mode": "SETPOINT", "manualOutput": 1.0, "setpointTarget": 1200.0}
```
When editing the file, mode can be set to OFF, MANUAL or SETPOINT.  For manual and setpoint operation the corresponding value should be set as desired.  
```
nano operation.json
# Update values and save
```
Updating the file change the operation of the controller even when the controller is running.  When updates are made through the REST endpoints, those updates write to operation.json first and then the change triggers the controller to update.

Profiles or ramps are not initiated from the operation.json file (see below for why).  Instead a profile is started and stopped using the REST endpoints.  This can be done on the command line as so,
```
# To start a profile, where <name> is the profile name
curl localhost:8080/mode/profile/start/<name>
# To stop a profile
curl localhost:8080/mode/profile/stop
```

### Reboots and Profiles
For OFF, MANUAL and SETPOINT mode, piddle will resume operation on boot.  If in SETPOINT mode,
and the temperature has deviated from the SETPOINT, piddle will ramp to the setpoint at the
rate specified in config.py.

Running a profile is not done in the operation.json file.  Profiles are initiated from the command
line/rest endpoint.  This is to avoid confusion with reboots and whether the profile was 
running/should be running and whether the process is so far out of whack that resuming a profile would be counter productive.  (TODO --> Profiles can be resumed on a restart, which will be a 
flag to the command to run them.)

### Viewing the Web Interface
On windows, navigate to your Pi's hostname:8080.  On linux or osx, navigate to your Pi's hostname.local:8080.

### Setting up as a Service
The application should be setup to run automatically as a daemon.  To do this do the following,
```
sudo cp systemd/piddle.service /etc/systemd/system
sudo systemctl daemon-reload
sudo systemctl enable piddle
sudo systemctl start piddle
```
This requires that the application is located in /home/pi/piddle.  If it is not, just edit the piddle.service file with the appropriate path.

### Setting up Multiple Controllers
The application is designed to support multiple temperature controllers using the same code base.  This allows you to have any number of these running, but be able to keep the configuration in one github repo or file share.  This way you do not have to keep track of several different configurations all living on different machines. Nor do you have to go to several different places to view the status over the web as the web interface grabs the list of servers from the configuration.  To this end, the config.py supports configuration by server name.  So you set the Pi host name (see below) and then add your settings to one copy of config.py.  This can then be shared between machines either manually or by forking this repo and cloning to each Pi once it is configured.

## Pi Setup Directions

How many times do we have to do this and how many times do we have to look it up.

Set the Pi Host Name
```
sudo nano /etc/hostname #Change name
sudo nano /etc/hosts    #Change 127.0.1.1 raspberrypi -> name
sudo reboot -h now
```

Standard Update, Build Tools and Node
```
sudo apt update
sudo apt full-upgrade
sudo apt-get install -y build-essential
sudo apt-get install -y git
```

Python Setup
```
# Package manager
sudo apt install python3-pip
# Install virtualenv underlying tool
sudo pip3 install virtualenv 
```

I2C Setup
```
#Turn on hardware support, enable I2C for MCP9600
sudo raspi-config
```

Timezone Configuration
```
#Go to localization
sudo raspi-config
```

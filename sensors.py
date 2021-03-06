import threading
import logging
import time
import datetime
import config
import mcp9600

log = logging.getLogger('file')

#Threaded class for reading from the thermocouple    
class TempSensor:
    def __init__(self, timeout=config.bad_thermocouple_read_timeout):
        self.temperature = 0
        self.coldJunction = 0
        self.failStart = 0
        self.failTimeout = timeout

        self.thermocouple = mcp9600.MCP9600()
        self.thermocouple._mcp9600.set('DEVICE_CONFIG', cold_junction_resolution=0.0625, adc_resolution=18, burst_mode_samples=1, shutdown_modes='Normal')
        self.thermocouple._mcp9600.set('THERMOCOUPLE_CONFIG', type_select=config.thermocouple_type, filter_coefficients=config.mcp9600_filter_coefficient)
        status=self.thermocouple._mcp9600.get('DEVICE_CONFIG')
        log.info('MCP9600 Config-> CJ Resolution: {} ADC Resolution: {}'.format(status.cold_junction_resolution, status.adc_resolution))
        status=self.thermocouple._mcp9600.get('THERMOCOUPLE_CONFIG')
        log.info('MCP9600 Config-> Thermocouple: {} Filter: {}'.format(status.type_select, status.filter_coefficients))
        for x in range(1, 5):
            self.thermocouple.clear_alert(x)
            self.thermocouple.configure_alert(x, enable=False)


    def clearAlert(self, alertOutputPin):
        self.thermocouple.clear_alert(alertOutputPin)

    def setAlert(self, target, latching, activeLogicLevel, alertOutputPin):
        # monitor_junction, 1 Cold Junction, 0 Thermocouple
        # rise_fall, 1 rising, 0 cooling
        # state, 1 active high, 0 active low
        # mode, 1 interrupt mode, 0 comparator mode
        inC = (target-32.0)*5.0/9.0
        self.thermocouple.configure_alert(alertOutputPin, monitor_junction=0, limit=inC, state=activeLogicLevel, mode=1 if latching else 0, enable=True, rise_fall=1)

    def update(self):
        try:
            temp = self.thermocouple.get_hot_junction_temperature()
            temp = temp*9.0/5.0 + 32
            self.temperature = temp 
            temp = self.thermocouple.get_cold_junction_temperature()
            temp = temp*9.0/5.0 + 32
            self.coldJunction = temp 
            self.failStart=None
        #After 60 fails, 
        except Exception:
            if self.failStart:
                if time.time > self.failStart+self.failTimeout:
                    raise      
            else:
                self.failStart = time.time()  

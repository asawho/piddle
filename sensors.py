import threading
import logging
import time
import datetime
import config

log = logging.getLogger()

#Import the right library
if config.max31855 + config.max6675 + config.max31855spi + config.mcp9600 > 1:
    log.error("choose (only) one converter IC")
    exit()
if config.max31855:
    from max31855 import MAX31855, MAX31855Error
    log.info("import MAX31855")
if config.max31855spi:
    import Adafruit_GPIO.SPI as SPI
    from max31855spi import MAX31855SPI, MAX31855SPIError
    log.info("import MAX31855SPI")
    spi_reserved_gpio = [7, 8, 9, 10, 11]
    if config.gpio_heat in spi_reserved_gpio:
        raise Exception("gpio_heat pin %s collides with SPI pins %s" % (config.gpio_heat, spi_reserved_gpio))
if config.max6675:
    from max6675 import MAX6675, MAX6675Error
    log.info("import MAX6675")
if config.mcp9600:
    import mcp9600
    log.info("import mcp9600")

#Threaded class for reading from the thermocouple    
class TempSensor:
    def __init__(self, timeout=config.bad_thermocouple_read_timeout):
        self.temperature = 0
        self.failStart = 0
        self.failTimeout = timeout

        if config.max6675:
            log.info("init MAX6675")
            self.thermocouple = MAX6675(config.gpio_sensor_cs,
                                     config.gpio_sensor_clock,
                                     config.gpio_sensor_data,
                                     config.temp_scale)

        if config.max31855:
            log.info("init MAX31855")
            self.thermocouple = MAX31855(config.gpio_sensor_cs,
                                     config.gpio_sensor_clock,
                                     config.gpio_sensor_data,
                                     config.temp_scale)

        if config.max31855spi:
            log.info("init MAX31855-spi")
            self.thermocouple = MAX31855SPI(spi_dev=SPI.SpiDev(port=0, device=config.spi_sensor_chip_id))

        if config.mcp9600:
            self.thermocouple = mcp9600.MCP9600()
            for x in range(1, 5):
                self.thermocouple.clear_alert(x)
                self.thermocouple.configure_alert(x, enable=False)

            self.thermocouple.get = self.thermocouple.get_hot_junction_temperature

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
            temp = self.thermocouple.get()
            if config.mcp9600:
                temp = temp*9.0/5.0 + 32
            self.temperature = temp 
            self.failStart=None
        #After 60 fails, 
        except Exception:
            if failStart:
                if time.time > failStart+self.failTimeout:
                    raise      
            else:
                failStart = time.time()  

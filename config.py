#######################################################################
#
#   General options

### Logging frequency in seconds
log_frequency = 30

### Server
listening_ip = "0.0.0.0"
listening_port = 8080

### duty cycle of the entire system in seconds. Every N seconds a decision
### is made about switching the relay[s] on & off and for how long.
### The thermocouple is read five times during this period and the highest
### value is used.
sensor_time_wait = 1

########################################################################
#
#   PID parameters

pid_kp = 0.03      # Proportional
pid_ki = 0.00025      # Integration
pid_kd = 0.0        # Derivative was 217

########################################################################
#
#   GPIO Setup (BCM SoC Numbering Schema)
#
#   Check the RasPi docs to see where these GPIOs are
#   connected on the P1 header for your board type/rev.
#   These were tested on a Pi B Rev2 but of course you
#   can use whichever GPIO you prefer/have available.

### Outputs
gpio_heat = [23,24]  # Switches zero-cross solid-state-relay

### Thermocouple Adapter selection:
#   max31855 - bitbang SPI interface
#   max31855spi - kernel SPI interface
#   max6675 - bitbang SPI interface
max31855 = 0
max6675 = 0
max31855spi = 0 # if you use this one, you MUST reassign the default GPIO pins
mcp9600 = 1
#How many seconds of failed thermocouple reads before raising an exception
bad_thermocouple_read_timeout = 60

### Thermocouple Connection (using bitbang interfaces)
gpio_sensor_cs = 27
gpio_sensor_clock = 22
gpio_sensor_data = 17

### Thermocouple SPI Connection (using adafrut drivers + kernel SPI interface)
spi_sensor_chip_id = 0


#!/usr/bin/env python
import mcp9600
import time

m = mcp9600.MCP9600()

print("Resetting alerts")
for x in range(1, 5):
    m.clear_alert(x)
    m.configure_alert(x, enable=False)

print("Configuring alerts")
#m.configure_alert(1, monitor_junction=0, limit=40, mode=1, enable=True)
#m.configure_alert(2, monitor_junction=0, limit=40, mode=1, enable=True, rise_fall=0)
#Non-Latching
#m.configure_alert(1, monitor_junction=0, limit=27, state=1, mode=0, enable=True, rise_fall=1)
#Latching
m.configure_alert(1, monitor_junction=0, limit=27, state=0, mode=1, enable=True, rise_fall=1)

count=0
while True:
    #print(time.time())
    t = m.get_hot_junction_temperature()
    c = m.get_cold_junction_temperature()
    d = m.get_temperature_delta()

    # alerts = m.check_alerts()

    # for x in range(1, 5):
    #     if alerts[x - 1] == 1:
    #         m.clear_alert(x)

    # print("Alerts: ", alerts)

    print("Hot: {}, Cold {}, Delta {}".format(t,c,d))
    #print("Hot: {}, Cold {}, Delta {}".format(t*9/5+32,c*9/5+32,d))

    time.sleep(1.0)
    count+=1
    if count == 5:
        #m.clear_alert(x)
        #m.configure_alert(x, enable=False)
        m.configure_alert(1, monitor_junction=0, limit=1, state=1, mode=0, enable=True, rise_fall=1)
        pass
    if count == 10:
        m.clear_alert(x)
        #m.configure_alert(x, enable=False)
        m.configure_alert(1, monitor_junction=0, limit=27, state=0, mode=1, enable=True, rise_fall=1)
        #m.clear_alert(x)
        pass


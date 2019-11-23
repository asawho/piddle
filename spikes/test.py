import threading
import time
import sched

# class Junk(threading.Thread):
#     def __init__(self):
#         threading.Thread.__init__(self)
#         self.daemon = True
#     def run(self):
#         try: 
#             while True:
#                 pass
#         except Exception as e:
#             print(e)
#             raise(e)

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)

#GPIO.setwarnings(False)
GPIO.setup(23, GPIO.OUT)

# j = Junk()
# j.start()
# time.sleep(1)
def calculateSleep():
    diff=0
    lastTime=time.time()
    count=0
    val=0
    while count < 1000:
        val=1-val
        GPIO.output(23, val)
        newTime=time.time()
        diff+=newTime-lastTime
        lastTime=newTime
        count+=1

    print(diff/1000)
calculateSleep()

# s = sched.scheduler()
# diff=0
# lastTime=time.time()
# count=0
# start = time.monotonic()
# def event():
#     global diff
#     global lastTime
#     newTime=time.time()
#     diff+=newTime-lastTime
#     lastTime=newTime

# while count < 1000:
#     s.enterabs(start+count/1000.0, 1, event)
#     count+=1
# s.run()
#print(diff/1000)



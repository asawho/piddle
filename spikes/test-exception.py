import os,signal
import time

try:
    def diedie(signum, frame):
       print("Died")
       raise Exception("your momma")
    signal.signal(signal.SIGINT, diedie)
    signal.signal(signal.SIGTERM, diedie)
    while True:
        #os.kill(os.getpid(), signal.SIGINT)
        print("one")
        time.sleep(1)
    #raise Exception("your momma")
except Exception as e:
    print(e)
finally:
    print("Go Joe!")
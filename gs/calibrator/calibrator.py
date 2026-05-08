from porthouse.gs.scheduler.interface import SchedulerInterface
from porthouse.gs.hardware.interface import RotatorInterface

import asyncio

SchedulerInterface.get_schedule()

class Calibrator:
    """Antenna calibration"""
    def __init__(self):
        self.el_angle = 0
        self.az_angle = 90
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.calibrator_task(), name="calibrator.calibrator_task")
    
    def calibrator_task(self):
        while True:
            await sched = SchedulerInterface.get_schedule()
            asyncio.sleep()
        
    def calibrate(self):
        # go to 90, 0 and calibrate that angle as 0
        await RotatorInterface.move(90,0)
        asyncio.sleep(45) #sleep 45 secs to verify that the movement is done
        await RotatorInterface.reset(90,0)
        pass
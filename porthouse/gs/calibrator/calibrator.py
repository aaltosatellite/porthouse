from porthouse.gs.scheduler.interface import SchedulerInterface
from porthouse.gs.hardware.interface import RotatorInterface
from porthouse.gs.tracking.utils import parse_time

from datetime import datetime, timedelta

import socket
import json
import struct
import sys
import traceback
import asyncio

SchedulerInterface.get_schedule()

class Calibrator:
    """Antenna calibration"""
    def __init__(self):
        self.el_angle = 0
        self.az_angle = 90
        
        #setup of multicast receiver socket for data
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.bind(("",6969))
        self.sock.settimeout(1.0)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, struct.pack("4sl", socket.inet_aton("224.0.0.1"), socket.INADDR_ANY))
        
        #sliding window for averaging last 5 measurements to counterract wind
        self.el_window = []
        
        #index of the last task after which the calibration was ran
        self.last_ran_index = 0
        
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.calibrator_task(), name="calibrator.calibrator_task")
    
    async def check_schedule(self, sched):
        previous_index = 0
        scheduled_index = 0
        prev_task = {}
        next_task = {}
        
        #get first task that is with the status "SCHEDULED"
        for task in sched:
            if task["status"] = "SCHEDULED":
                next_task = task
                previous_index = scheduled_index-1
                prev_task = sched[previous_index]
            else:
                scheduled_index+=1
        
        #check if next task is more than 10 minutes away
        next_starting = parse_time(next_task["start_time"]).utc_datetime()
        if next_starting-datetime.utcnow() > timedelta(minutes=10):
            #check that we are at least 5 mins away from last flyby
            prev_ending = parse_time(prev_task["end_time"]).utc_datetime()
            if datetime.utcnow()-prev_ending > timedelta(minutes=5):
                return (True, previous_index)
        return (False, -1)
                
    
    async def calibrator_task(self):
        while True:
            sched = await SchedulerInterface.get_schedule(verbose=False)
            
            query_result = await self.check_schedule(sched)
            if query_result[0] && query_result[1] != last_ran_index:
                #don't run calibration multiple times in a row between the same 2 passes
                last_ran_index = query_result[1]
                self.log.debug("Calibration: Open window detected, starting automatic antenna calibration")
                await calibrate()
            else:
                await asyncio.sleep(10)
            
    
    async def get_data(self):
        #gather 50 samples of data from the last 10 seconds
        while len(self.el_window<50):
            try:
                data, addr = sock.recvfrom(65536)
                
                #load JSON
                parsed_data = json.loads(data.decode())
                
                self.el_window.append(parsed_data[app_el])
                
                await asyncio.sleep(0.2)
                
            except KeyboardInterrupt:
                print("Keyboardinterrupt")
                raise KeyboardInterrupt #Raising this so that the rest of the system can do what it wishes with it
            except TimeoutError:
                pass
            except:
                print(traceback.format_exc())
    
    async def calibrate(self):
        # go to 90, 0 and calibrate that angle as 0
        try:
            self.log.debug("Calibration: Pointing antenna to east...")
            await RotatorInterface.move(90,0,False)
            asyncio.sleep(45) #sleep 45 secs to verify that the movement is done
            self.log.debug("Calibration: Gathering data...")
            await get_data() #gather data from antenna sensors
            
            average_el = sum(self.el_window)/50 #get average from the 10 second window
            
            self.log.debug("Calibration: calibrating...")
            await RotatorInterface.reset(90,average_el)
            await RotatorInterface.move(90,0,False)
            await RotatorInterface.set_tracking(True) #go back to tracking afterwards
            self.log.debug("Calibration completed successfully!")
        finally:
            await RotatorInterface.set_tracking(True)
            self.log.debug("Calibration issue")
        pass
#from porthouse.gs.scheduler.interface import SchedulerInterface
#from porthouse.gs.hardware.interface import RotatorInterface
from porthouse.gs.tracking.utils import parse_time

from porthouse.core.basemodule_async import BaseModule, RPCError, rpc, queue, bind
from porthouse.core.rpc_async import send_rpc_request

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
        #setup of multicast receiver socket for data
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.bind(("",6969))
        self.sock.settimeout(1.0)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, struct.pack("4sl", socket.inet_aton("224.0.0.1"), socket.INADDR_ANY))
        
        #sliding window for averaging last 5 measurements to counterract wind
        self.el_window = []
        self.az_window = []
        
        self.window_length = 5
        
        #index of the last task after which the calibration was ran
        self.last_ran_task = ""
        
        #loop = asyncio.get_event_loop()
        #task = loop.create_task(self.calibrator_task(), name="calibrator.calibrator_task")
    
    
    
    @queue()
    #will automatically run this if there's a LOS event
    @bind(exchange="event", routing_key="los")
    async def check_schedule(self, sched):
        processes = await send_rpc_request("scheduler", "rpc.get_processes", data)
        previous_index = 0
        scheduled_index = 0
        prev_task = {}
        next_task = {}
        
        #TODO check which rotator it is supposed to be
        #TODO maybe just subscribe to task_end with some decorator
        #get first task that is with the status "SCHEDULED"
        for task in sched:
            if task["status"] == "SCHEDULED":
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
                
    
    @rpc()
    @bind(exchange="calibrator", routing_key="rpc.#", prefixed=True)
    async def rpc_handler(self, request_name, request_data):
        print("calibracion would do something here nprobably")
    
    
    async def calibrator_task(self):
        while True:
            sched = await SchedulerInterface.get_schedule(verbose=False)
            
            query_result = await self.check_schedule(sched)

            if (query_result[0]) and (query_result[1] != last_ran_index):
                #don't run calibration multiple times in a row between the same 2 passes
                last_ran_index = query_result[1]
                self.log.debug("Calibration: Open window detected, starting automatic antenna calibration")
                await calibrate()
            else:
                await asyncio.sleep(10)
    
    
    async def get_data(self):
        #gather 5 samples of data from the last 10 seconds
        while len(self.el_window<self.window_length):
            try:
                data, addr = sock.recvfrom(65536)
                
                #load JSON
                parsed_data = json.loads(data.decode())
                
                self.el_window.append(parsed_data[app_el])
                self.az_window.append(parsed_data[app_az])
                
                await asyncio.sleep(2)
                
            except KeyboardInterrupt:
                print("Keyboardinterrupt")
                raise KeyboardInterrupt #Raising this so that the rest of the system can do what it wishes with it
            except TimeoutError:
                pass
            except:
                print(traceback.format_exc())
    
    async def calibrate(self):
        #go to 90, 0 and calibrate that angle as 0
        try:
            self.log.debug("Calibration: Pointing antenna to east...")
            await RotatorInterface.move(90,0,False)
            moving = True
            while moving: #Check if movement is done
                asyncio.sleep(5)
                status = RotatorInterface.status(verbose=False)
                if (round(status["az"]) == 90) and (round(status["el"]) == 0):
                    moving = False
                else:
                    self.log.debug("Calibration: Movement not finished yet...")
            
            self.log.debug("Calibration: Gathering data...")
            await get_data() #gather data from antenna sensors
            
            average_el = sum(self.el_window)/self.window_length #get average from the 10 second window
            
            self.log.debug("Calibration: calibrating elevation...")
            await RotatorInterface.reset_position(90,average_el)
            
            #move back to 90,0 for azimuth calib
            await RotatorInterface.move(90,0,False)
            moving = True
            while moving: 
                asyncio.sleep(5)
                status = RotatorInterface.status(verbose=False)
                if (round(status["az"])) == 90 and (round(status["el"]) == 0):
                    moving = False
                else:
                    self.log.debug("Calibration: Movement not finished yet...")
            
            
            self.log.debug("Calibration: Gathering data...")
            await get_data()
            
            average_az = sum(self.az_window)/self.window_length
            
            self.log.debug("Calibration: calibrating azimuth...")
            await RotatorInterface.reset_position(average_az,0)
            
            self.log.debug("Calibration completed successfully!")
        except:
            self.log.error("Calibration issue!")
        finally:
            self.log.debug("Enabling tracking...")
            await RotatorInterface.set_tracking(True) #go back to tracking afterwards
        pass
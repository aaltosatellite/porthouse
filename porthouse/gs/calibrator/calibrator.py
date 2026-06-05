from porthouse.gs.tracking.utils import parse_time

from porthouse.core.basemodule_async import BaseModule, RPCError, rpc, queue, bind
from porthouse.core.rpc_async import send_rpc_request

from datetime import datetime, timedelta, timezone

import socket
import json
import struct
import sys
import traceback
import asyncio


class Calibrator(BaseModule):
    """Antenna calibration"""
    def __init__(self, 
            calibration_enabled = False,
            max_calibration_cycles = 15,
            **kwargs):
        
        #setup of all basic module stuff
        super().__init__(**kwargs)
        
        #sliding window for averaging last 5 measurements to counterract wind
        self.el_window = []
        self.az_window = []
        
        self.window_length = 5
        
        self.max_calibration_cycles = max_calibration_cycles
        self.calibration_enabled = calibration_enabled
        
        #index of the last task after which the calibration was ran (not needed as we use LOS events now so if there's no LOS event then no calibration occurs)
        #self.last_ran_task = "" 
        
        #loop = asyncio.get_event_loop()
        #task = loop.create_task(self.calibrator_task(), name="calibrator.calibrator_task")
    
    
    

#-----------------------Command handling-----------------
    @rpc()
    @bind(exchange="calibrator", routing_key="rpc.#", prefixed=True)
    async def rpc_handler(self, request_name, request_data):
        if request_name == "rpc.calibration":
            """
                Enable/disable calibration
            """

            # Parse parameters
            try:
                enabled = request_data["enabled"]
            except (KeyError, ValueError):
                raise RPCError("Invalid or missing mode parameter 'enabled'")
            
            self.calibration_enabled = enabled
            self.log.info("Automatic calibration is now "+ ("enabled" if enabled else "disabled"))
        elif request_name == "rpc.cycle_count":
            try:
                cycle_count = request_data["cycle_count"]
            except:
                raise RPCError("Invalid or missing mode parameter 'cycle_count'")
            
            if cycle_count < 1:
                raise RPCError("Cycle count must be higher than 0")
            else:
                self.max_calibration_cycles = cycle_count
        elif request_name == "rpc.calibrate":
            self.log.info("Automatic calibration command issued, starting calibration")
            await self.calibrate()
        elif request_name == "rpc.status":
            return {
                "enabled":self.calibration_enabled,
                "max_calibration_cycles":self.max_calibration_cycles}
                





#-----------------------Helper funcs---------------------
    async def get_data(self):
        #gather 5 samples of data from the last 10 seconds
        start_time = datetime.utcnow()
        self.el_window.clear()
        self.az_window.clear()
        
        #setup of multicast receiver socket for data
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.bind(("",6969))
        sock.settimeout(2.0)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, struct.pack("4sl", socket.inet_aton("224.0.0.1"), socket.INADDR_ANY))
        
        while len(self.el_window)<self.window_length:
            try:
                #kill it if data acquisition takes too long
                if datetime.utcnow()-start_time > timedelta(seconds=60):
                    return
                    
                
                
                data, addr = sock.recvfrom(65536)
                
                #load JSON
                parsed_data = json.loads(data.decode())
                
                self.el_window.append(parsed_data["app_el"])
                self.az_window.append(parsed_data["app_az"])
                
                await asyncio.sleep(2)
            except KeyboardInterrupt:
                print("Keyboardinterrupt")
                sock.close()
                raise KeyboardInterrupt #Raising this so that the rest of the system can do what it wishes with it
            except TimeoutError:
                pass
            except:
                print(traceback.format_exc())
        sock.close()


    async def are_we_there_yet(self,az,el):
        moving = True
        while moving: 
            await asyncio.sleep(5)
            status = await self.send_rpc_request("rotator", "uhf.rpc.status")
            if ((abs(status["az"])-az) < 1) and ((abs(status["el"]-el)) < 1):
                moving = False
                return
            else:
                self.log.debug("Movement not finished yet...")
                # for some reason the rotation sometimes just stops for no reason
                await self.send_rpc_request("rotator", f"uhf.rpc.rotate", {
                    "az": az, "el": el, "shortest": False
                })




#-----------------------Rotator logic--------------------------------
    @queue()
    #will automatically run this if there's a LOS event
    @bind(exchange="event", routing_key="los")
    async def check_schedule(self):
        if not self.calibration_enabled():
            return
        
        next_task = []
        data = {"process_name": None, "target": None, "rotators": ["uhf"], "status": None, "limit": None}
        schedule = await self.send_rpc_request("scheduler", "rpc.get_schedule", data)
        
        
        #get first task that is with the status "SCHEDULED"
        for task in schedule:
            if task["status"] == "ONGOING": #ongoing task, abort
                return
            if task["status"] == "SCHEDULED":
                next_task = task
        
        
        #check if next task is more than 10 minutes away
        next_starting = parse_time(next_task["start_time"]).utc_datetime().replace(tzinfo=timezone.utc)
        if next_starting-datetime.utcnow().replace(tzinfo=timezone.utc) > timedelta(minutes=10):
            self.log.info("Open window detected, starting automatic antenna calibration")
            await self.calibrate()



    async def calibrate(self):
        #go to 90, 0 and calibrate that angle as 0
        self.log.info("Calibration starting")
        try:
            calibrating = True
            cycle_count = 0
            while calibrating:
                self.log.info("Pointing antenna to east...")
                await self.send_rpc_request("rotator", f"uhf.rpc.rotate", {
                    "az": 90, "el": 0, "shortest": False
                })
                await self.are_we_there_yet(90,0)
                
                
                #-------------Elevation------------------
                self.log.info("Gathering data...")
                await self.get_data() #gather data from antenna sensors
                
                average_el = sum(self.el_window)/self.window_length #get average from the 10 second window
                
                self.log.info("calibrating elevation...")
                await self.send_rpc_request("rotator", f"uhf.rpc.reset_position", {
                    "az": 90, "el": average_el
                }, timeout=5)
                
                #wait to move back to 90,0 for azimuth calib
                await self.are_we_there_yet(90,0)
                
                
                #-------------Azimuth-------------------
                self.log.info("Gathering data...")
                await self.get_data()
                
                average_az = sum(self.az_window)/self.window_length
                
                self.log.info("calibrating azimuth...")
                await self.send_rpc_request("rotator", f"uhf.rpc.reset_position", {
                    "az": average_az, "el": 0
                }, timeout=5)
                
                await self.are_we_there_yet(90,0)
                
                
                #-------------Verification--------------
                await self.get_data()
                self.log.info(str(self.az_window))
                self.log.info(str(self.el_window))
                az_offset = abs(90-sum(self.az_window)/self.window_length)
                el_offset = abs( 0-sum(self.el_window)/self.window_length)
                cycle_count+=1
                if az_offset < 2 and el_offset < 1:
                   calibrating=False
                else:
                    self.log.info("Calibration results not satisfactory:")
                    self.log.info(f"Azimuth offset:   {az_offset}")
                    self.log.info(f"Elevation offset: {el_offset}")
                    
                    #check how many cycles
                    if cycle_count>self.max_calibration_cycles:
                        self.log.error(f"{self.max_calibration_cycles} calibration retries exceeded!")
                        raise TimeoutError

                    #check that it's not already time for the next task:
                    data = {"process_name": None, "target": None, "rotators": ["uhf"], "status": None, "limit": None}
                    schedule = await self.send_rpc_request("scheduler", "rpc.get_schedule", data)
                    for task in schedule:
                        if task["status"] == "ONGOING": #ongoing task!!!!!!!
                            self.log.error("Next task already running!!!")
                            raise TimeoutError
                        if task["status"] == "SCHEDULED":
                            next_starting = parse_time(task["start_time"]).utc_datetime().replace(tzinfo=timezone.utc)
                            if next_starting-datetime.utcnow().replace(tzinfo=timezone.utc) <= timedelta(minutes=5):
                                self.log.info("Time until next task <= 5 minutes!")
                                raise TimeoutError
                    
                    self.log.info("Recalibrating...")
                
            self.log.info("Calibration completed successfully!")
        except:
            self.log.error("Calibration issue!")
            self.log.error(traceback.format_exc())
        finally:
            self.log.info("Enabling tracking...")
            #go back to tracking afterwards
            await self.send_rpc_request("rotator", f"uhf.rpc.tracking", {
                "mode": "automatic"
            })
        pass
"""
    Housekeeping backend service
"""
from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Optional, Union
from datetime import datetime, timezone, timedelta
from porthouse.mcs.packet_measurements.database import MeasurementsDatabase
from ..utils import WebRPCError

class MeasurementsService:

    def __init__(self, server: OpenMCTBackend, db_url: str, satellite: str):
        """
        Initialize measurements service.
        """
        self.satellite = satellite
        self.server = server
        self.db = MeasurementsDatabase(db_url)
        self.subscriptions = {}


    def rpc_command(self, client, method, params):
        """
        """
        if method == "history":
            """
                Return measurement history
            """
            try:
                data = self.db.query(params["fields"],
                                     params["options"]["start"],
                                     params["options"]["end"])
            except TypeError as e:
                if "missing" in str(e):
                    arg = str(e).split("'")[1]
                    raise WebRPCError(f"Request missing argument {arg!r}")
                elif "unexpected" in str(e):
                    arg = str(e).split("'")[1]
                    raise WebRPCError(f"Unknown argument {arg!r}")
                raise
            return {
                "measurements": data
            }

        elif method == "latest":

            try:
                # Get latest signal data measurements
                latest = self.db.query_latest(**params)
            except TypeError as e:
                if "missing" in str(e):
                    arg = str(e).split("'")[1]
                    raise WebRPCError(f"Request missing argument {arg!r}")
                elif "unexpected" in str(e):
                    arg = str(e).split("'")[1]
                    raise WebRPCError(f"Unknown argument {arg!r}")
                raise

            return {
                "measurements": latest
            }
        elif method == "get_schema":
            """
                Return the schema for measurements
            """
            # Specific to Foresail-1p for now, should be generalized later
            return {
            "key": "fs1p",
            "name": "Foresail-1p",
            "fields": [
                {"key": "absolute_rx_frequency",
                 "name": "Absolute RX Frequency",
                 "format_type": "float",
                 "unit": "Hz"},
                {"key": "payload_power",
                 "name": "Payload Power",
                 "format_type": "float",
                 "unit": "W"},
                {"key": "noise_power",
                 "name": "Noise Power",
                 "format_type": "float",
                 "unit": "W"},
                 {"key": "signal_to_noise_ratio",
                 "name": "Signal to Noise Ratio",
                 "format_type": "float",
                 "unit": "dB"},
                {"key": "power_bandwidth",
                 "name": "Power Bandwidth",
                "format_type": "float",
                "unit": "Hz"},
                {"key": "baudrate",
                 "name": "Baudrate",
                 "format_type": "number",
                 "unit": "bps"},
            ]
            }
        elif method == "subscribe":
            self.subscriptions[client] = True

        elif method == "unsubscribe":
            del self.subscriptions[client]
        else:
            raise WebRPCError(f"No such command: {method!r}")

    async def handle_subscription(self, message: Dict):
        """
        Distribute new measurements to subscribers.

        Args:
            message:
        """
        # Check which clients wants the data
        for client in self.server.clients:
            if client not in self.subscriptions:
                continue
            await client.send_json(
                subscription={
                    "service": "measurements",
                    "subsystem": "measurements",
                    "utc": message["utc"],
                    "measurements": message["fields"]
                }
            )



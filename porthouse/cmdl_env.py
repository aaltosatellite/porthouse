from datetime import datetime
from porthouse.core.rpc_async import send_rpc_request



async def log():
    """
        Get latest log messages
    """
    for line in send_rpc_request("log", "rpc.get_history", {}).get("entries", []):
        line["created"] = datetime.fromtimestamp(line["created"]).strftime('%Y-%m-%d %H:%M:%S')
        print("{created} - {module} - {level} - {message}".format(**line))

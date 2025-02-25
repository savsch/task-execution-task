import time

def get_timestamp() -> int:
    """Returns the current timestamp in ms, similar to Date.now() in js"""
    return int(time.time()*1000)
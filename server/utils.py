import time

def get_timestamp() -> int:
    """Returns the current timestamp in ms, similar to Date.now() in js"""
    return int(time.time()*1000)

def bytes_to_string(byte_data: bytes) -> str:
    try:
        return byte_data.decode('utf-8')
    except UnicodeDecodeError:
        return f"[Binary Data, size {len(byte_data)} bytes]"

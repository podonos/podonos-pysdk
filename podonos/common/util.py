import time
import uuid


def generate_random_name():
    current_time_milliseconds = int(time.time() * 1000)
    random_uuid = uuid.uuid4()
    return f"{current_time_milliseconds}-{random_uuid}"

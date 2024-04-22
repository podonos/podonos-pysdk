"""
Functions for evaluation name
"""

import datetime


def generate_random_eval_name() -> str:
    cur = datetime.datetime.now()
    return f'{cur.year}{cur.month}{cur.day}{cur.hour}{cur.minute}{cur.second}'

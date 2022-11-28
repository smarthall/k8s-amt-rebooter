import time

import kopf
import logging


def is_ready(obj, **_):
    return False


def is_not_ready(obj, **_):
    return not is_ready(obj)


def past_reboot(obj, **_):
    return False


def should_reboot(obj, **_):
    return is_not_ready(obj) and past_reboot(obj)


# Node went offline
@kopf.on.update(
    "nodes",
    annotations={"me.danielhall.amt-rebooter/reboot-at": kopf.ABSENT},
    when=is_not_ready,
)
def node_went_offline(stopped, **kwargs):
    pass


# Node came back online
@kopf.on.update(
    "nodes",
    annotations={"me.danielhall.amt-rebooter/reboot-at": kopf.PRESENT},
    when=is_ready,
)
def node_back_online(stopped, **kwargs):
    pass


# If we need to do a reboot (we might need a daemon to trigger this one)
@kopf.on.update(
    "nodes",
    annotations={"me.danielhall.amt-rebooter/reboot-at": kopf.PRESENT},
    when=should_reboot,
)
def node_needs_reboot(stopped, **kwargs):
    pass

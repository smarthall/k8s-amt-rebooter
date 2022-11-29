import time

import kopf
import kubernetes
import logging


reboot_scheduled_annotation = "me.danielhall.amt-rebooter/reboot-at"


def is_ready(status, **_):
    conditions = status.get("conditions", None)

    if conditions is None:
        return False

    ready_conditions = list(filter(lambda x: x["type"] == "Ready", conditions))

    if len(ready_conditions) != 1:
        return False

    ready_status = ready_conditions[0]["status"]

    return ready_status.lower() == "true"


def is_not_ready(status, **_):
    return not is_ready(status)

def past_reboot(new, **_):
    return False


def should_reboot(new, **_):
    return is_not_ready(new) and past_reboot(new)


# Node went offline
@kopf.on.update(
    "nodes",
    annotations={reboot_scheduled_annotation: kopf.ABSENT},
    when=is_not_ready,
)
def node_went_offline(name, **kwargs):
    logging.info(f'Node {name} just went offline')


# Node came back online
@kopf.on.update(
    "nodes",
    annotations={reboot_scheduled_annotation: kopf.PRESENT},
    when=is_ready,
)
def node_back_online(**kwargs):
    pass


# If we need to do a reboot (we might need a daemon to trigger this one)
@kopf.on.update(
    "nodes",
    annotations={"me.danielhall.amt-rebooter/reboot-at": kopf.PRESENT},
    when=should_reboot,
)
def node_needs_reboot(**kwargs):
    pass

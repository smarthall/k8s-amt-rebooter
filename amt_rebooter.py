import time

import kopf
import logging


reboot_scheduled_annotation = "me.danielhall.amt-rebooter/reboot-at"
failed_node_timeout_seconds = 30


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


def get_reboot_time(metadata):
    annotations = metadata.get("annotations", None)
    if annotations is None:
        return None

    time_string = annotations.get(reboot_scheduled_annotation, None)
    if time_string is None:
        return None

    return float(time_string)


def should_reboot(metadata):
    return get_reboot_time(metadata) < time.time()


def reboot_node(name, body):
    pass


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    settings.posting.enabled = False


# Node went offline
@kopf.on.update(
    "nodes",
    annotations={reboot_scheduled_annotation: kopf.ABSENT},
    when=is_not_ready,
)
def node_went_offline(name, patch, **kwargs):
    logging.info(f"Node {name} just went offline")

    patch["metadata"] = {
        "annotations": {
            reboot_scheduled_annotation: str(time.time() + failed_node_timeout_seconds)
        }
    }

    return


# Node came back online
@kopf.on.update(
    "nodes",
    annotations={reboot_scheduled_annotation: kopf.PRESENT},
    when=is_ready,
)
def node_back_online(name, patch, **kwargs):
    logging.info(f"Node {name} came back online")

    patch["metadata"] = {"annotations": {reboot_scheduled_annotation: None}}

    return


# Wait the right amount of time before we trigger the reboot
@kopf.daemon(
    "nodes",
    annotations={"me.danielhall.amt-rebooter/reboot-at": kopf.PRESENT},
    when=is_not_ready,
)
def node_pending_reboot(name, body, stopped, meta, **kwargs):
    while not stopped:
        if should_reboot(meta):
            logging.info(f"Node {name} is about to be rebooted")
            reboot_node(name, body)
            # TODO: Don't trigger the reboot repetitively

        stopped.wait(1)

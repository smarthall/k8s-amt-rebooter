import time
import logging

import kopf
import amt.client
import amt.wsman
import yaml


config_filename = 'config.yaml'
reboot_scheduled_annotation = "me.danielhall.amt-rebooter/reboot-at"
failed_node_timeout_seconds = 300


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


def lookup_node_config(name):
    config = {}
    with open(config_filename, 'r') as f:
        config = yaml.safe_load(f)
    
    return config.get(name, None)

def reboot_node(name):
    node_config = lookup_node_config(name)

    if node_config is None:
        logging.info(f'Could not find "{name}" in configuration, ignoring...')
        return

    if len({'address', 'password', 'username'}.intersection(set(node_config.keys()))) != 3:
        logging.error(f'Invalid configuration for node "{name}", ignoring...')
        return

    client = amt.client.Client(node_config.get('address'), node_config.get('password'), node_config.get('username'))

    power_state = client.power_status()
    if power_state != '2':
        friendly_power_state = amt.wsman.friendly_power_state(power_state)
        logging.warn(f'Node "{name}" found in unexpected power state "{friendly_power_state}", not rebooting...')
        return

    client.power_cycle()

    logging.info(f"Node {name} has been power cycled")


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
            reboot_node(name, body)
            # TODO: Don't trigger the reboot repetitively

        stopped.wait(1)

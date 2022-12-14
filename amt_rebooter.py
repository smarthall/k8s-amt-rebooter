import time
import logging

import kopf
import amt.client
import amt.wsman
import yaml
from kubernetes import client


config_filename = "config.yaml"
reboot_scheduled_annotation = "me.danielhall.amt-rebooter/reboot-at"
reboot_count_annotation = "me.danielhall.amt-rebooter/reboot-count"
failed_node_timeout_seconds = 120
max_reboot_count = 5
reboot_backoff_seconds = 60


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


def should_reboot(metadata, attempts):
    return get_reboot_time(metadata) < time.time() and attempts < max_reboot_count


def lookup_node_config(name):
    config = {}
    with open(config_filename, "r") as f:
        config = yaml.safe_load(f)

    return config.get(name, None)


def reboot_node(name):
    node_config = lookup_node_config(name)

    if node_config is None:
        logging.info(f'Could not find "{name}" in configuration, ignoring...')
        return

    if (
        len({"address", "password", "username"}.intersection(set(node_config.keys())))
        != 3
    ):
        logging.error(f'Invalid configuration for node "{name}", ignoring...')
        return

    client = amt.client.Client(
        node_config.get("address"),
        node_config.get("password"),
        node_config.get("username"),
    )

    power_state = client.power_status()
    if power_state != "2":
        friendly_power_state = amt.wsman.friendly_power_state(power_state)
        logging.warn(
            f'Node "{name}" found in unexpected power state "{friendly_power_state}", not rebooting...'
        )
        return

    client.power_cycle()


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
            reboot_scheduled_annotation: str(time.time() + failed_node_timeout_seconds),
            reboot_count_annotation: str(0),
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

    patch["metadata"] = {
        "annotations": {
            reboot_scheduled_annotation: None,
            reboot_count_annotation: None,
        }
    }

    return


# Wait the right amount of time before we trigger the reboot
@kopf.daemon(
    "nodes",
    annotations={"me.danielhall.amt-rebooter/reboot-at": kopf.PRESENT},
    when=is_not_ready,
)
def node_pending_reboot(name, body, stopped, meta, **kwargs):
    while not stopped:
        attempts = int(meta.get("annotations", {}).get(reboot_count_annotation, 0))

        if should_reboot(meta, attempts):
            api = client.CoreV1Api()
            try:
                reboot_node(name)
            except Exception as e:
                attempts += 1
                api.patch_node(
                    name,
                    {
                        "metadata": {
                            "annotations": {
                                reboot_scheduled_annotation: str(
                                    time.time()
                                    + failed_node_timeout_seconds
                                    + (reboot_backoff_seconds * attempts)
                                ),
                                reboot_count_annotation: str(attempts),
                            }
                        }
                    },
                )
                logging.info(f'An exception occurred while trying to reboot {name}, attempt {attempts}')
                logging.info(str(e))
                continue

            api.delete_node(name)
            logging.info(f"Node {name} has been power cycled, removed from k8s so it can reregister")

        stopped.wait(1)

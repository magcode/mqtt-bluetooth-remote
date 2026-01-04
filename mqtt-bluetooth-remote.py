from malog import setupLogging
import asyncio
import signal
import hid
import json
from pathlib import Path
import aiomqtt
from dbus_next.aio import MessageBus
from dbus_next import BusType, Message, MessageType, Variant
from device import DeviceConfig
import argparse
import time


async def repeatKey(val):
    first = True
    while True:
        logger.debug("Sending " + str(val))
        global mqttClient
        await mqttClient.publish(topic + "/" + val, payload=val)
        if first:
            await asyncio.sleep(0.4)
            first = False
        else:
            await asyncio.sleep(0.2)


async def singleKey(val):
    logger.debug("Sending " + str(val))
    global mqttClient
    await mqttClient.publish(topic + "/" + val, payload=val)


async def getBattery(mac):
    message = Message(
        destination="org.bluez",
        path="/org/bluez/hci0/dev_" + mac,
        interface="org.freedesktop.DBus.Properties",
        signature="ss",
        member="Get",
        body=["org.bluez.Battery1", "Percentage"],
    )
    if messageBus:
        result = await messageBus.call(message)
        if result.message_type is MessageType.ERROR:
            logger.warning("Could not read battery")
            return 0

        if type(result.body[0]) is Variant:
            return result.body[0].value

    return 0


async def sendStatus(online, battery=None):
    if online:
        logger.debug("Connection Watcher OK")
        await mqttClient.publish(topic + "/status", payload="online")
        if battery and mqttClient:
            await mqttClient.publish(topic + "/battery", payload=battery)
    else:
        if mqttClient:
            await mqttClient.publish(topic + "/status", payload="offline")


async def watchConnection():
    try:
        while True:
            await asyncio.sleep(10)
            try:
                hidDevice.get_product_string()
                serial = hidDevice.get_serial_number_string().replace(":", "_").upper()
                battery = await getBattery(serial)
                await sendStatus(True, battery)
            except IOError:
                await sendStatus(False)
            except aiomqtt.MqttError as err:
                logger.info(f"mqtt error: {err}")
    except asyncio.CancelledError:
        logger.debug("Connection Watcher Task cancelled - stopping.")


async def pollHid(deviceConfig: DeviceConfig):
    global reptask
    global stack

    keys = deviceConfig.getKeys()
    releaseKeys = deviceConfig.getReleaseKeys()
    noRepeatKeys = deviceConfig.getNoRepeatKeys()

    last_key = None
    last_time = 0
    current_time = 0
    COOLDOWN_TIME = 0.4

    while True:
        try:
            data = hidDevice.read(8)
            if data:
                value = f"{data[0]}-{data[1]}-{data[2]}-{data[3]}"

                if value and (value in keys or value in releaseKeys):
                    if value not in releaseKeys:
                        key = keys[value]
                        current_time = time.time()
                        time_diff = current_time - last_time
                        logLine = (
                            f"Press:  {key} LastKey: {last_key} LastTime: {last_time:.2f} TimeDiff: {time_diff:.2f}"
                        )

                        if key == last_key:
                            if time_diff < COOLDOWN_TIME:
                                logger.info(logLine + " Skipped")
                                stack.append(key)
                                continue

                        logger.info(logLine)
                        last_time = current_time
                        if reptask:
                            reptask.cancel()
                        stack.append(key)

                        if value in noRepeatKeys:
                            await singleKey(key)
                        else:
                            reptask = asyncio.create_task(repeatKey(key), name="repeater")
                            logger.debug("stack:" + str(stack))

                        last_key = key
                    else:
                        # happens in two cases: normal key release or power button (for sony)
                        # if it was a normal key release, there is still an entry in the stack
                        key = releaseKeys[value]

                        stackSize = len(stack)
                        if stackSize == 0:
                            logger.info(f"Release Stack: {stack}, sending POWER")
                            await singleKey(key)
                        else:
                            logger.info(f"Release Stack: {stack}, clearing stack")
                            stack.pop(0)
                            reptask.cancel()
                else:
                    logger.warning("Unknown key: " + value)
            await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.debug("HID Polling Task cancelled - stopping.")
            if hidDevice:
                hidDevice.close()


async def connectDBus():
    global messageBus
    messageBus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    if messageBus:
        logger.info("DBus connected")
    else:
        logger.error("DBus connection failed")


async def connectHid(deviceConfig: DeviceConfig, ready_event: asyncio.Event):
    global hidDevice
    try:
        hidDevice = hid.device()
        hidDevice.open(deviceConfig.getVendorId(), deviceConfig.getProductId())
        hidDevice.set_nonblocking(True)
        logger.info(f"Hid {deviceConfig.getName()} Connected")
        ready_event.set()
    except Exception as e:
        logger.error(f"Failed to connect HID device: {e}")


async def mqttLoop(host, port, user, password):
    while True:
        try:
            async with aiomqtt.Client(
                hostname=host, port=port, username=user, password=password, identifier="remote_" + config["DEVICE_TYPE"]
            ) as client:
                logger.info("MQTT connected")
                global mqttClient
                mqttClient = client
                while True:
                    await asyncio.sleep(1)

        except aiomqtt.MqttError as e:
            logger.error(f"MQTT Error: {e}. Reconnect in 5 sec ...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Unexpected MQTT error: {e}")
            await asyncio.sleep(5)


def getConfig():
    parser = argparse.ArgumentParser(description="MQTT Bluetooth Remote")
    parser.add_argument("--config", default="config.json", help="Configuration file name")
    args = parser.parse_args()
    configFile = Path(__file__).with_name(args.config)
    with configFile.open("r") as jsonfile:
        config = json.load(jsonfile)
        return config


async def shutdown(signame, stop_event):
    logger.info(f"Signal {signame} received. Shutting down program...")
    stop_event.set()  # This wakes up the main() function


async def main():
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for signame in ("SIGINT", "SIGTERM"):
        loop.add_signal_handler(
            getattr(signal, signame), lambda s=signame: asyncio.create_task(shutdown(s, stop_event))
        )

    hid_ready_signal = asyncio.Event()
    loop.create_task(connectHid(deviceConfig, hid_ready_signal), name="connectHid")

    try:
        await asyncio.wait_for(hid_ready_signal.wait(), timeout=5.0)
        logger.info("HID device connected successfully.")
    except asyncio.TimeoutError:
        logger.error("HID device could not be connected. Exiting.")
        return

    loop.create_task(connectDBus(), name="connectDBus")
    loop.create_task(
        mqttLoop(
            host=config["MQTT_HOST"],
            port=config["MQTT_PORT"],
            user=config["MQTT_USERNAME"],
            password=config["MQTT_PASSWORD"],
        ),
        name="mqtt",
    )
    loop.create_task(watchConnection(), name="watch")
    loop.create_task(pollHid(deviceConfig), name="hidpoll")

    await stop_event.wait()
    logger.info("Cleanup ...")
    await sendStatus(False)

    # Kill all running tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        logger.info(f"Cancelling task: {task.get_name()}")
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("All tasks finished. Exit.")


if __name__ == "__main__":
    mqttClient = None
    messageBus = None
    hidDevice = None
    reptask = None
    config = getConfig()
    loop = None
    logger = setupLogging(config)
    logger.info("Started")

    topic = config["MQTT_TOPIC"]
    deviceConfig = DeviceConfig(deviceName=config["DEVICE_TYPE"])
    stack = []
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

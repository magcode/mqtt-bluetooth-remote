import asyncio
import signal
import hid
import json
from pathlib import Path
import aiomqtt
import logging
from dbus_next.aio import MessageBus
from dbus_next import BusType, Message, MessageType, Variant
from device import DeviceConfig
import argparse
from logging.config import dictConfig
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
        if battery:
            await mqttClient.publish(topic + "/battery", payload=battery)
    else:
        logger.error("Connection Watcher Not connected")
        await mqttClient.publish(topic + "/status", payload="offline")


async def watchConnection():
    while True:
        try:
            await asyncio.sleep(10)
            hidDevice.get_product_string()
            serial = hidDevice.get_serial_number_string()
            serial = serial.replace(":", "_").upper()
            battery = await getBattery(serial)
            await sendStatus(True, battery)
        except IOError:
            await sendStatus(False)
        except aiomqtt.exceptions.MqttCodeError as err:
            logger.info("mqtt error: " + str(err))
        except asyncio.CancelledError:
            logger.debug("Connection Watcher shutdown")


async def pollHid(deviceConfig: DeviceConfig):
    global reptask
    global stack
    exceptionCount = 0
    keys = deviceConfig.getKeys()
    releaseKeys = deviceConfig.getReleaseKeys()
    noRepeatKeys = deviceConfig.getNoRepeatKeys()


    last_data = None
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
                        logger.debug("data received: " + str(data) + " last_data: " + str(last_data))
                        key = keys[value]
                        if data == last_data:
                            current_time = time.time()
                            logger.debug("timing current:" + str(current_time) + " last_time:" + str(last_time))
                            if data[1] != 0 and (current_time - last_time) < COOLDOWN_TIME:
                                # Ignoriere dieses Event, da es zu schnell nach dem letzten kam
                                logger.warning("Ignoriere schnellen Wiederholungsevent current time:" + str(current_time) + " last_time:" + str(last_time))
                                stack.append(key)
                                continue
                        
                        logger.info(f"Key pressed: {value}  - {key}")
                        last_time = current_time
                        if reptask:
                            reptask.cancel()
                        stack.append(key)

                        if value in noRepeatKeys:
                            await singleKey(key)
                        else:
                            reptask = asyncio.create_task(repeatKey(key), name="repeater")
                            logger.debug("stack:" + str(stack))
                        last_data = data
                    else:
                        # happens in two cases: normal key release or power button (for sony)
                        # if it was a normal key release, there is still an entry in the stack
                        key = releaseKeys[value]
                        logger.info("stack:" + str(stack))
                        stackSize = len(stack)
                        if stackSize == 0:
                            await singleKey(key)
                        else:
                            logger.debug("Keyup release")
                            stack.pop(0)
                            reptask.cancel()
                            logger.debug("Current stack:" + str(stack))
                    
                else:
                    logger.warning("Unknown key: " + value)
            await asyncio.sleep(0.1)
        except Exception as e:
            if exceptionCount < 10:
                logger.error("Error when reading hid" + str(e))
                exceptionCount = exceptionCount + 1
                break
    await exit_prog("SIGINT")


async def connectDBus():
    global messageBus
    messageBus = await MessageBus(bus_type=BusType.SYSTEM).connect()


async def connectHid(deviceConfig: DeviceConfig):
    global hidDevice
    hidDevice = hid.device()
    hidDevice.open(deviceConfig.getVendorId(), deviceConfig.getProductId())
    hidDevice.set_nonblocking(True)
    logger.info(f"Hid {deviceConfig.getName()} Connected")


async def setupMQTT(host, port, user, password):
    global mqttClient
    mqttClient = aiomqtt.Client(
        port=port, password=password, username=user, hostname=host, identifier="remote" + config["DEVICE_TYPE"]
    )
    await mqttClient.__aenter__()


async def exit_prog(signame):
    logger.info("got signal %s: exit" % signame)
    await sendStatus(False)
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    for task in tasks:
        task.cancel()
    await asyncio.sleep(1)
    loop.stop()
    logger.info("Exit")


def getConfig():
    parser = argparse.ArgumentParser(description="MQTT Bluetooth Remote")
    parser.add_argument("--config", default="config.json", help="Configuration file name")
    args = parser.parse_args()
    configFile = Path(__file__).with_name(args.config)
    with configFile.open("r") as jsonfile:
        config = json.load(jsonfile)
        return config


mqttClient = None
messageBus = None
hidDevice = None
reptask = None
config = getConfig()

# load logging configuration
with open("logging_config.json", "r") as f:
    logging_config = json.load(f)
    dictConfig(logging_config)


logger = logging.getLogger("remote-" + config["DEVICE_TYPE"])
logger.info("Started")

topic = config["MQTT_TOPIC"]
deviceConfig = DeviceConfig(deviceName=config["DEVICE_TYPE"])
stack = []
loop = asyncio.get_event_loop()
for signame in ("SIGINT", "SIGTERM"):
    loop.add_signal_handler(getattr(signal, signame), lambda signame=signame: asyncio.create_task(exit_prog(signame)))

loop.create_task(connectDBus(), name="connectDBus")
loop.create_task(connectHid(deviceConfig), name="connectHid")
loop.create_task(
    setupMQTT(
        host=config["MQTT_HOST"],
        port=config["MQTT_PORT"],
        user=config["MQTT_USERNAME"],
        password=config["MQTT_PASSWORD"],
    ),
    name="mqtt",
)
loop.create_task(watchConnection(), name="watch")
loop.create_task(pollHid(deviceConfig), name="hidpoll")
loop.run_forever()

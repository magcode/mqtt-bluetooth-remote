import asyncio
import signal
import hid
import json
from pathlib import Path
import aiomqtt
import logging
from devices.RMFTX621E import keys
import colorlog
from colorlog import ColoredFormatter
from logging_loki import LokiHandler, emitter
from dbus_next.aio import MessageBus
from dbus_next import BusType, Message, MessageType, Variant


async def repeatKey(val):
    while True:
        logger.debug("Sending " + str(val))
        global mqttClient
        await mqttClient.publish(topic + "/" + val, payload=val)
        await asyncio.sleep(0.25)


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
        except asyncio.CancelledError:
            logger.debug("Connection Watcher shutdown")

        try:
            hidDevice.get_product_string()
            serial = hidDevice.get_serial_number_string()
            serial = serial.replace(":", "_").upper()
            battery = await getBattery(serial)
            await sendStatus(True, battery)
        except IOError:
            await sendStatus(False)
        except aiomqtt.exceptions.MqttCodeError as err:
            logger.info("mqtt error: " + str(err))


async def pollHid():
    global reptask
    global stack
    while True:
        data = hidDevice.read(4)
        if data:
            value = str(data[1]) + "-" + str(data[2])
            if value and value in keys:
                key = keys[value]

                if key != keys["0-0"]:
                    logger.info("Key pressed: " + str(data) + " - " + value + " - " + key)
                    stack.append(key)
                    if reptask:
                        reptask.cancel()
                    reptask = asyncio.create_task(repeatKey(key), name="repeater")
                    logger.debug("Stack:" + str(stack))
                else:
                    stackSize = len(stack)
                    if stackSize == 0:
                        logger.info("Sending KEY_POWER")
                        await mqttClient.publish(topic + "/KEY_POWER", payload="KEY_POWER")
                    else:
                        logger.debug("Keyup")
                        stack.pop(0)
                        reptask.cancel()
                        logger.debug("Current stack:" + str(stack))
            else:
                logger.error("Unknown key " + value)
        await asyncio.sleep(0.1)

async def connectDBus():
    global messageBus
    messageBus = await MessageBus(bus_type=BusType.SYSTEM).connect()

async def connectHid():
    global hidDevice
    hidDevice = hid.device()
    hidDevice.open(1356, 3469)
    hidDevice.set_nonblocking(True)
    logger.info("Hid Connected")


async def setupMQTT(host, port, user, password):
    global mqttClient
    mqttClient = aiomqtt.Client(bind_port=port, password=password, username=user, hostname=host)
    await mqttClient.__aenter__()


async def ask_exit(signame):
    logger.info("got signal %s: exit" % signame)
    await sendStatus(False)
    # await mqttClient.__aexit__()
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    for task in tasks:
        task.cancel()
    await asyncio.sleep(1)
    loop.stop()
    logger.info("Exit")


def getConfig():
    configFile = Path(__file__).with_name("config.json")
    with configFile.open("r") as jsonfile:
        config = json.load(jsonfile)
        return config


def setupLogging(
    logger,
):
    logger.setLevel(config["LOG_LEVEL"])
    lokiEnabled = config["LOG_LOKI"]
    lokiUrl = config["LOKI_URL"]
    if lokiEnabled:
        emitter.LokiEmitter.level_tag = "level"
        loggingHandler = LokiHandler(url=lokiUrl + "/loki/api/v1/push", tags={"monitor": "grafana"}, version="1")
        # loggingHandler.setLevel(lokiLevel.upper())
        logger.addHandler(loggingHandler)

    consoleEnabled = config["LOG_CONSOLE"]
    if consoleEnabled:
        handler = colorlog.StreamHandler()
        formatter = ColoredFormatter(
            "%(asctime)s %(log_color)s%(levelname)-8s%(reset)s %(white)s%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            reset=True,
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
            secondary_log_colors={},
            style="%",
        )
        handler.setFormatter(formatter)
        # handler.setLevel(consoleLevel.upper())
        logger.addHandler(handler)


mqttClient = None
messageBus = None
hidDevice = None
reptask = None
config = getConfig()

logger = logging.getLogger("sonyremote")
setupLogging(logger)
logger.info("Started")

topic = config["MQTT_TOPIC"]
stack = []
loop = asyncio.get_event_loop()
for signame in ("SIGINT", "SIGTERM"):
    loop.add_signal_handler(getattr(signal, signame), lambda signame=signame: asyncio.create_task(ask_exit(signame)))

loop.create_task(connectDBus(), name="connectDBus")
loop.create_task(connectHid(), name="connectHid")
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
loop.create_task(pollHid(), name="hidpoll")
loop.run_forever()

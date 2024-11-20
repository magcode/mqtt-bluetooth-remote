# WORK IN PROGRESS

# Bluetooth remote MQTT gateway

This tool allows you to use a Bluetooth remote controls as an universal input for your home automation.

Currently supported:

["Sony RMF-TX621E remote control"](https://www.google.com/search?q=RMF-TX621E)

You need a linux machine. It is verified working with Debian 10.

# What it does
* Once running you will receive MQTT messages if you press buttons on the remote.
* On a regular schedule the status of the remote is published.
* On a regular schedule the battery level of the remote is published.

# Step 2: Configure
You need to configure the tool in the file `config.yaml`.

```
todo

```

## Auto repeat
For some keys (e.g. `KEY_VOLUMEUP`) you may want auto-repeat. If you hold the key multiple MQTT messages will be triggered.


## Get Bluetooth remote connected
You need to pair and connect your Bluetooth remote before you can use it with this tool.

Best is to use Linux' `bluetoothctl` tool.


# Step 3: Install
```
TODO
```

# Start/stop
```
sudo service mqblre start
sudo service mqblre stop
```

# Uninstall
```
sudo service mqblre stop
TODO
```

# Using it

## Normal key press
If you press a button you will find the following MQTT message triggered:

```
home/room/remote/KEY_MUTE trigger
```
## Long press with "autoRepeat"
If you keep pressing one of the supported "autoRepeat" buttons you will trigger multiple MQTT messages

```
home/room/remote/KEY_VOLUMEUP trigger
home/room/remote/KEY_VOLUMEUP trigger
home/room/remote/KEY_VOLUMEUP trigger
```


# Notes
* None


# Openhab integration

Example things file
```
Thing mqtt:topic:RoomRemote "Room Remote" (mqtt:broker:mosquitto) {
    Channels:
        Type string : KEY_UP "KEY_UP" [ stateTopic="home/room/remote/KEY_UP", trigger=true]
        Type string : KEY_DOWN "KEY_DOWN" [ stateTopic="home/room/remote/KEY_DOWN", trigger=true]
        Type string : KEY_ENTER "KEY_ENTER" [ stateTopic="home/room/remote/KEY_ENTER", trigger=true]
        Type string : KEY_LEFT "KEY_LEFT" [ stateTopic="home/room/remote/KEY_LEFT", trigger=true]
        Type string : KEY_RIGHT "KEY_RIGHT" [ stateTopic="home/room/remote/KEY_RIGHT", trigger=true]
        Type string : KEY_HOMEPAGE "KEY_HOMEPAGE" [ stateTopic="home/room/remote/KEY_HOMEPAGE", trigger=true]
        Type string : KEY_VOLUMEUP "KEY_VOLUMEUP" [ stateTopic="home/room/remote/KEY_VOLUMEUP", trigger=true]
        Type string : KEY_VOLUMEDOWN "KEY_VOLUMEDOWN" [ stateTopic="home/room/remote/KEY_VOLUMEDOWN", trigger=true]
        Type string : KEY_BACK "KEY_BACK" [ stateTopic="home/room/remote/KEY_BACK", trigger=true]
        Type string : KEY_PREVIOUSSONG "KEY_PREVIOUSSONG" [ stateTopic="home/room/remote/KEY_PREVIOUSSONG", trigger=true]
        Type string : KEY_NEXTSONG "KEY_NEXTSONG" [ stateTopic="home/room/remote/KEY_NEXTSONG", trigger=true]
        Type string : KEY_POWER "KEY_POWER" [ stateTopic="home/room/remote/KEY_POWER", trigger=true]
        Type string : KEY_PLAYPAUSE "KEY_PLAYPAUSE" [ stateTopic="home/room/remote/KEY_PLAYPAUSE", trigger=true]
        Type string : KEY_MUTE "KEY_MUTE" [ stateTopic="home/room/remote/KEY_MUTE", trigger=true]
        Type string : KEY_MUTE-LONG "KEY_MUTE-LONG" [ stateTopic="home/room/remote/KEY_MUTE-LONG", trigger=true]
        Type string : KEY_BACKSPACE "KEY_BACKSPACE" [ stateTopic="home/room/remote/KEY_BACKSPACE", trigger=true]
        Type string : KEY_COMPOSE "KEY_COMPOSE" [ stateTopic="home/room/remote/KEY_COMPOSE", trigger=true]        
}
```

Example rules file
```
rule "KEY_BACK"
    when
        Channel "mqtt:topic:RoomRemote:KEY_BACK" triggered
    then
        // what you want
end
```

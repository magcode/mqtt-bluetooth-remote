user=`whoami`
homepath=`echo $HOME`
__service="
[Unit]
Description=MQTT Bluetooth Remote
#Wants=network-online.target
After=bluetooth.service

[Service]
Type=simple
User=$user
Group=input
WorkingDirectory=$homepath/mqtt-bluetooth-remote
ExecStart=$homepath/venv1/bin/python3 $homepath/mqtt-bluetooth-remote/mqtt-bluetooth-remote.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
"

echo "$__service" | sudo tee /lib/systemd/system/mqblre.service

sudo systemctl daemon-reload
sudo systemctl enable mqblre.service
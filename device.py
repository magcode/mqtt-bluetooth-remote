import json
from pathlib import Path


class DeviceConfig:
    def __init__(self, deviceName):
        self.name = deviceName
        current_file_path = Path(__file__).resolve()
        devices_path = current_file_path.parent / "devices"
        spec_file = devices_path / (deviceName + ".json")
        with spec_file.open("r") as jsonfile:
            spec = json.load(jsonfile)
            self.vendorId = spec["vendorId"]
            self.productId = spec["productId"]
            self.keys = spec["keys"]
            self.releaseKeys = spec["releaseKeys"]
            self.noRepeatKeys = spec["noRepeatKeys"]

    def getProductId(self):
        return self.productId

    def getVendorId(self):
        return self.vendorId

    def getName(self):
        return self.name

    def getKeys(self):
        return self.keys

    def getReleaseKeys(self):
        return self.releaseKeys

    def getNoRepeatKeys(self):
        return self.noRepeatKeys

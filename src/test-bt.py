import asyncio
from bleak import BleakClient, BleakScanner
from paho.mqtt import client as mqtt_client
import json
import logging
import sys
import os
from time import time 

FORMAT = '%(asctime)s:%(levelname)s: %(message)s'
logging.basicConfig(stream=sys.stdout, level="INFO", format=FORMAT)
log = logging.getLogger("")

'''
Very basic attempt to just report Solarflow Hub's stats to mqtt for local long-term tests
'''

address = os.environ.get('SF_BT_ADDR',"94:C9:60:3E:C8:E7")
MQTT_HOST = os.environ.get('MQTT_HOST',"192.168.1.245")
MQTT_PORT = os.environ.get('MQTT_PORT',1883)
WIFI_PWD = os.environ.get('WIFI_PWD',None)
WIFI_SSID = os.environ.get('WIFI_SSID',None)
SF_DEVICE_ID = os.environ.get('SF_DEVICE_ID',None)
local_broker = MQTT_HOST
local_port = MQTT_PORT
local_client: mqtt_client


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("Connected to MQTT Broker!")
    else:
        log.error("Failed to connect, return code %d\n", rc)

async def local_mqtt_connect():
    global local_client
    global local_port
    local_client = mqtt_client.Client(client_id="solarflow-bt")
    local_client.connect(local_broker,local_port)
    local_client.on_connect = on_connect

def getInfo(client):
    global local_client
    char = "0000c304-0000-1000-8000-00805f9b34fb"
    cmd = {"deviceId":"5ak8yGU7","messageId":"none","method":"getInfo","timestamp": str(int(time())) }

    try:
        b = bytearray()
        b.extend(map(ord, json.dumps(cmd)))
        client.write_gatt_char(char,b,response=False)
    except Exception:
        log.exception("Getting device Info failed")

def set_IoT_Url(client):
    global local_client
    char = "0000c304-0000-1000-8000-00805f9b34fb"
    cmd1 = '{"iotUrl":"{}","messageId":"1002","method":"token","password":"{}","ssid":"{}","timeZone":"GMT+08:00","token":"abcdefgh"}'.format(MQTT_HOST,MQTT_PORT,WIFI_PWD,WIFI_SSID)

    cmd2 = '{"messageId":"1003","method":"station"}'

    reply = '{"messageId":123,"timestamp":'+str(int(time()))+',"params":{"token":"abcdefgh","result":0}}'
    
    try:
        b = bytearray()
        b.extend(map(ord, cmd1))
        client.write_gatt_char(char,b,response=False)
    except Exception:
        log.exception("Setting reporting URL failed")

    
    try:
        b = bytearray()
        b.extend(map(ord, cmd2))
        client.write_gatt_char(char,b,response=False)
    except Exception:
        log.exception("Setting WiFi Mode failed")


    local_client.publish("iot/73bkTV/5ak8yGU7/register/replay",reply)
    


def handle_rx(BleakGATTCharacteristic, data: bytearray):
    payload = json.loads(data.decode("utf8"))
    log.info(payload)

    if "method" in payload and payload["method"] == "BLESPP":
        log.info(f'The SF device id is: {payload["deviceId"]}')

    if "properties" in payload:
        props = payload["properties"]

        for prop, val in props.items():
            local_client.publish(f'solarflow-hub/telemetry/{prop}',val)

        # also report whole state to mqtt (nothing coming from cloud now :-)
        local_client.publish("SKC4SpSn/5ak8yGU7/state",json.dumps(payload["properties"]))
    
    if "packData" in payload:
        packdata = payload["packData"]
        if len(packdata) > 0:
            for pack in packdata:
                sn = pack.pop('sn')
                for prop, val in pack.items():
                    local_client.publish(f'solarflow-hub/telemetry/batteries/{sn}/{prop}',val)


async def main():

    device = await BleakScanner.find_device_by_filter(
                lambda d, ad: d.name and d.name.lower().startswith("zen")
            )

    log.info("Found device: " + str(device))

    async with BleakClient(device) as client:
        svcs = client.services
        log.info("Services:")
        for service in svcs:
            log.info(service)

        await local_mqtt_connect()

        #await set_IoT_Url(client)

        await getInfo(client)

        while True:
            char = "0000c305-0000-1000-8000-00805f9b34fb"
            await client.start_notify(char,handle_rx)


asyncio.run(main())
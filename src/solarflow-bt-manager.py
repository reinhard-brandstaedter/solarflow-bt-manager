#!/usr/bin/python3

import asyncio
from bleak import BleakClient, BleakScanner
from paho.mqtt import client as mqtt_client
import json
import logging
import sys
import getopt
import os
import time

FORMAT = '%(asctime)s:%(levelname)s: %(message)s'
logging.basicConfig(stream=sys.stdout, level="INFO", format=FORMAT)
log = logging.getLogger("")

'''
Very basic attempt to just report Solarflow Hub's stats to mqtt for local long-term tests
'''

SF_COMMAND_CHAR = "0000c304-0000-1000-8000-00805f9b34fb"
SF_NOTIFY_CHAR = "0000c305-0000-1000-8000-00805f9b34fb"

WIFI_PWD = os.environ.get('WIFI_PWD',None)
WIFI_SSID = os.environ.get('WIFI_SSID',None)
SF_DEVICE_ID = os.environ.get('SF_DEVICE_ID',None)
SF_PRODUCT_ID = os.environ.get('SF_PRODUCT_ID','73bkTV')
GLOBAL_INFO_POLLING_INTERVAL = os.environ.get('GLOBAL_INFO_POLLING_INTERVAL', 60)
mqtt_user = os.environ.get('MQTT_USER',None)
mqtt_pwd = os.environ.get('MQTT_PWD',None)
mq_client: mqtt_client = None
bt_client: BleakClient

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("Connected to MQTT Broker!")
    else:
        log.error("Failed to connect, return code %d\n", rc)

def local_mqtt_connect(broker, port):
    client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION1, client_id="solarflow-bt")
    if mqtt_user is not None and mqtt_pwd is not None:
        client.username_pw_set(mqtt_user, mqtt_pwd)
    client.connect(broker,port)
    client.on_connect = on_connect
    return client

async def getInfo(client):
    info_cmd = {"messageId":"none","method":"getInfo","timestamp": str(int(time.time())) }
    properties_cmd = {"method":"read", "timestamp": str(int(time.time())), "messageId": "none","properties":["getAll"]}

    try:
        b = bytearray()
        b.extend(map(ord, json.dumps(info_cmd)))
        await client.write_gatt_char(SF_COMMAND_CHAR,b,response=False)
    except Exception:
        log.exception("Getting device Info failed")

    try:
        b = bytearray()
        b.extend(map(ord, json.dumps(properties_cmd)))
        await client.write_gatt_char(SF_COMMAND_CHAR,b,response=False)
    except Exception:
        log.exception("Getting device Info failed")

async def set_IoT_Url(client,broker,port,ssid,deviceid):
    global mq_client, SF_PRODUCT_ID
    c1 = {'iotUrl':broker,
          'messageId':'1002',
          'method': 'token',
          'password': WIFI_PWD,
          'ssid': ssid,
          'timeZone':'GMT+02:00',
          'token':'abcdefgh'}
    cmd1 = json.dumps(c1)
    cmd2 = '{"messageId":"1003","method":"station"}'

    reply = '{"messageId":123,"timestamp":'+str(int(time.time()))+',"params":{"token":"abcdefgh","result":0}}'

    try:
        b = bytearray()
        b.extend(map(ord, cmd1))
        log.info(cmd1)
        await client.write_gatt_char(SF_COMMAND_CHAR,b,response=False)
    except Exception:
        log.exception("Setting reporting URL failed")

    try:
        b = bytearray()
        b.extend(map(ord, cmd2))
        await client.write_gatt_char(SF_COMMAND_CHAR,b,response=False)
    except Exception:
        log.exception("Setting WiFi Mode failed")

    if mq_client:
        mq_client.publish(f'iot/{SF_PRODUCT_ID}/{deviceid}/register/replay', reply, retain=True)


def handle_rx(BleakGATTCharacteristic, data: bytearray):
    global mq_client, SF_PRODUCT_ID, SF_DEVICE_ID
    payload = json.loads(data.decode("utf8"))
    log.info(payload)

    if "method" in payload and payload["method"] == "getInfo-rsp":
        log.info(f'The SF device ID is: {payload["deviceId"]}')
        log.info(f'The SF device SN is: {payload["deviceSn"]}')


    if mq_client:
        if "properties" in payload:
            props = payload["properties"]

            for prop, val in props.items():
                mq_client.publish(f'solarflow-hub/telemetry/{prop}',val)

            # also report whole state to mqtt (nothing coming from cloud now :-)
            mq_client.publish(f"{SF_PRODUCT_ID}/{SF_DEVICE_ID}/state",json.dumps(payload["properties"]))

        if "packData" in payload:
            packdata = payload["packData"]
            if len(packdata) > 0:
                for pack in packdata:
                    sn = pack.pop('sn')
                    for prop, val in pack.items():
                        mq_client.publish(f'solarflow-hub/telemetry/batteries/{sn}/{prop}',val)


async def run(broker=None, port=None, info_only: bool = False, connect: bool = False, disconnect: bool = False, ssid=None, deviceid=None):
    global mq_client
    global bt_client
    global SF_PRODUCT_ID
    product_class = None

    if SF_PRODUCT_ID == '73bkTV':
      product_class = "zenp"
    elif SF_PRODUCT_ID == 'A8yh63': 
      product_class = "zenh"
    elif SF_PRODUCT_ID == 'yWF7hV':
      product_class = "zenr"
    else:
      product_class = "zen"

    log.info("scan for: " + str(product_class))

    device = await BleakScanner.find_device_by_filter(
                lambda d, ad: d.name and d.name.lower().startswith(product_class)
            )

    if device:
        log.info("Found device: " + str(device))

        async with BleakClient(device) as bt_client:
            svcs = bt_client.services
            log.info("Services:")
            for service in svcs:
                log.info(service)

            if broker and port:
                mq_client = local_mqtt_connect(broker,port)

            if disconnect and broker and port and ssid and SF_DEVICE_ID:
                await set_IoT_Url(bt_client,broker,port,ssid,SF_DEVICE_ID)
                log.info("Setting IoTURL connection parameters - disconnect")
                await asyncio.sleep(30)
                return

            if connect and ssid:
                await set_IoT_Url(bt_client,"mq.zen-iot.com",1883,ssid,SF_DEVICE_ID)
                log.info("Setting IoTURL connection parameters - connect")
                await asyncio.sleep(30)
                return

            if info_only and broker is None:
                await bt_client.start_notify(SF_NOTIFY_CHAR,handle_rx)
                await getInfo(bt_client)
                await asyncio.sleep(20)
                await bt_client.stop_notify(SF_NOTIFY_CHAR)
                return
            else:
                getinfo = True
                while True:
                    await bt_client.start_notify(SF_NOTIFY_CHAR,handle_rx)
                    # fetch global info every GLOBAL_INFO_POLLING_INTERVAL seconds
                    if getinfo:
                        await getInfo(bt_client)
                        getinfo = False
                    getinfo = await asyncio.sleep(int(GLOBAL_INFO_POLLING_INTERVAL), True)
    else:
        log.info("No Solarflow device found! You can try these steps:\n \
                  - Move closer to the hub\n \
                  - Reset your bluetooth connection (bluetoothctl)\n \
                  - Restart the Solarflow Hub\n \
                  - Disconnect any mobile Apps currently connected to the hub")

def main(argv):
    global mqtt_user, mqtt_pwd
    ssid = None
    mqtt_broker= mqtt_port = None
    connect = disconnect = info_only = False
    opts, args = getopt.getopt(argv,"hidb:u:p:w:c")
    for opt, arg in opts:
        if opt == '-h':
            print('solarflow-bt-manager.py [ -i | -d | -c ]')
            print(' -i\tprint some information about the hub and exit')
            print(' -d\tdisconnect the hub from Zendure cloud')
            print(' -b\thostname:port of local MQTT broker')
            print(' -w\tWiFi SSID the hub should be connected to')
            print(' -c\tconnect the hub to Zendure cloud')
            sys.exit()
        elif opt in ("-i", "--info"):
            info_only = True
            disconnect = connect = False
        elif opt in ("-d", "--disconnect"):
            disconnect = True
            connect = False
        elif opt in ("-w", "--wifi"):
            ssid = arg
        elif opt in ("-b", "--mqtt_broker"):
            parts = arg.split(':')
            mqtt_broker = parts[0]
            mqtt_port = int(parts[1]) if len(parts) > 1 else 1883
        elif opt in ("-u", "--mqtt_user"):
            mqtt_user = arg
        elif opt in ("-p", "--mqtt_pwd"):
            mqtt_pwd = arg
        elif opt in ("-c", "--connect"):
            connect = True
            disconnect = False

    if disconnect:
        if ssid is None:
            print("Disconnecting from Zendure cloud requires a WiFi SSID (-w)!")
            sys.exit()
        if mqtt_broker is None:
            print("Disconnecting from Zendure cloud requires a local MQTT broker (-b)!")
            sys.exit()
        if WIFI_PWD is None:
            print(f'Please provide password for WiFi SSID "{ssid}" via environment variable WIFI_PWD')
            sys.exit()
        if SF_DEVICE_ID is None:
            print("Please provide your device ID via environment variable SF_DEVICE_ID")
            sys.exit()
        if SF_PRODUCT_ID is None:
            print("Please provide your product ID via environment variable SF_PRODUCT_ID (73bkTV for Hub1200, A8yh63 for Hub2000, yWF7hV for AIO2400")
            sys.exit()
        print("Disconnecting Solarflow Hub from Zendure Cloud")

    if connect:
        print("Connecting Solarflow Hub Back to Zendure Cloud")

    asyncio.run(run(broker=mqtt_broker, port=mqtt_port, info_only=info_only, connect=connect, disconnect=disconnect, ssid=ssid))

if __name__ == '__main__':
    main(sys.argv[1:])

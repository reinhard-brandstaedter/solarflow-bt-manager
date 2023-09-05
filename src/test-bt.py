import asyncio
from bleak import BleakClient, BleakScanner
from paho.mqtt import client as mqtt_client
import json
import logging
import sys
import getopt
import os
import time 
import atexit

FORMAT = '%(asctime)s:%(levelname)s: %(message)s'
logging.basicConfig(stream=sys.stdout, level="INFO", format=FORMAT)
log = logging.getLogger("")

'''
Very basic attempt to just report Solarflow Hub's stats to mqtt for local long-term tests
'''

SF_COMMAND_CHAR = "0000c304-0000-1000-8000-00805f9b34fb"
SF_NOTIFY_CHAR = "0000c305-0000-1000-8000-00805f9b34fb"

address = os.environ.get('SF_BT_ADDR',"94:C9:60:3E:C8:E7")
WIFI_PWD = os.environ.get('WIFI_PWD',None)
WIFI_SSID = os.environ.get('WIFI_SSID',None)
mq_client: mqtt_client = None
bt_client: BleakClient
_connected = []


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("Connected to MQTT Broker!")
    else:
        log.error("Failed to connect, return code %d\n", rc)

def local_mqtt_connect(broker, port):
    client = mqtt_client.Client(client_id="solarflow-bt")
    client.connect(broker,port)
    client.on_connect = on_connect
    return client

async def getInfo(client):
    info_cmd = {"deviceId":"5ak8yGU7","messageId":"none","method":"getInfo","timestamp": str(int(time.time())) }
    properties_cmd = {"method":"read", "timestamp": str(int(time.time())), "messageId": "none","deviceId": "5ak8yGU7","properties":["getAll"]}

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

def set_IoT_Url(client):
    global mq_client
    cmd1 = '{"iotUrl":"{}","messageId":"1002","method":"token","password":"{}","ssid":"{}","timeZone":"GMT+08:00","token":"abcdefgh"}'.format(MQTT_HOST,MQTT_PORT,WIFI_PWD,WIFI_SSID)
    cmd2 = '{"messageId":"1003","method":"station"}'

    reply = '{"messageId":123,"timestamp":'+str(int(time.time()))+',"params":{"token":"abcdefgh","result":0}}'
    
    try:
        b = bytearray()
        b.extend(map(ord, cmd1))
        client.write_gatt_char(SF_COMMAND_CHAR,b,response=False)
    except Exception:
        log.exception("Setting reporting URL failed")

    try:
        b = bytearray()
        b.extend(map(ord, cmd2))
        client.write_gatt_char(SF_COMMAND_CHAR,b,response=False)
    except Exception:
        log.exception("Setting WiFi Mode failed")


    mq_client.publish("iot/73bkTV/5ak8yGU7/register/replay",reply)


def handle_rx(BleakGATTCharacteristic, data: bytearray):
    global mq_client
    payload = json.loads(data.decode("utf8"))
    log.info(payload)

    if "method" in payload and payload["method"] == "BLESPP":
        log.info(f'The SF device id is: {payload["deviceId"]}')

    if mq_client:
        if "properties" in payload:
            props = payload["properties"]

            for prop, val in props.items():
                mq_client.publish(f'solarflow-hub/telemetry/{prop}',val)

            # also report whole state to mqtt (nothing coming from cloud now :-)
            mq_client.publish("SKC4SpSn/5ak8yGU7/state",json.dumps(payload["properties"]))
        
        if "packData" in payload:
            packdata = payload["packData"]
            if len(packdata) > 0:
                for pack in packdata:
                    sn = pack.pop('sn')
                    for prop, val in pack.items():
                        mq_client.publish(f'solarflow-hub/telemetry/batteries/{sn}/{prop}',val)


async def run(broker=None, port=None, info_only: bool = False, connect: bool = False, disconnect: bool = False):
    global mq_client
    global bt_client
    device = await BleakScanner.find_device_by_filter(
                lambda d, ad: d.name and d.name.lower().startswith("zen")
            )

    log.info("Found device: " + str(device))

    async with BleakClient(device) as bt_client:
        _connected.append(bt_client)
        svcs = bt_client.services
        log.info("Services:")
        for service in svcs:
            log.info(service)

        if broker and port:
            mq_client = local_mqtt_connect(broker,port)

        if disconnect and broker and port:
            await set_IoT_Url(bt_client,broker,port)

        if info_only:
            await getInfo(bt_client)

        while True:
            await bt_client.start_notify(SF_NOTIFY_CHAR,handle_rx)

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
            print(' -d\tconnect the hub to Zendure cloud')
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
            mqtt_port = parts[1] if len(parts) > 1 else 1883
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
            print('Please provide password for WiFi SSID {ssid} via environment variable WIFI_PWD')
    
    if connect:
        print("Connecting Solarflow Hub Back to Zendure Cloud")

    asyncio.run(run(broker=mqtt_broker, port=mqtt_port, info_only=info_only, connect=connect, disconnect=disconnect))

async def _destroy(self):
    log.info("Cleanup BT Connections")
    await asyncio.wait([client.disconnect() for client in _connected], return_when=asyncio.ALL_COMPLETED)
    _connected = []

@atexit.register
def _destroy():
    asyncio.get_event_loop().run_until_complete(_destroy())

if __name__ == '__main__':
    main(sys.argv[1:])
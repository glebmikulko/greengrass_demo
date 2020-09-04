
# AWS Greengrass demo

## Overview

![Schema][schema]

The main entities of this repo are Robot and KC (Robot Coordinator).
KC always knows the state of the Robot (will be described later how). When the robot becomes idle KC sends new order to the robot (operation **1**) in the following format:
```python
{
	"order_id": order_id,
	'ingredients': [...]
}
```
All communication here and further happens via MQTT. The Robot listens to the corresponding MQTT topic (`robots/Robot1/process_order`) and starts "preparing" the order. During this simulation, the robot sends updates of its internal state (shadow) to the IoT Core (operation **2**).  The state of the robot is represented with the following fields:
```python
{
	'thing_name': Robot1,
	'idle': False,
	'order_id': 14,
	'paused':  False,
}
```
KC monitors changes in the Robot's shadow (operation **3**) and knows when it becomes idle.
On the schema above and in the description only one Robot was used. But the setup works with multiple robots at one time in the same fashion. For this, you need to run multiple Robot scripts (see below).

## Logs
KC logs
```
Subscribing to topic '$aws/things/+/shadow/update/accepted'...
Subscribed with QoS.AT_LEAST_ONCE
Robot Robot1 is idle: True
Sending next order 63 to the robot Robot1
Robot Robot1 is idle: False
Robot Robot1 is idle: False
Robot Robot1 is idle: False
Robot Robot1 is idle: False
Robot Robot1 is idle: True
```
Robot logs
```
Subscribing to topic 'robots/Robot1/process_order'...
Subscribed with QoS.AT_LEAST_ONCE
Send shadow update request with order_id None.
Received message from topic 'robots/Robot1/process_order': b'{"order_id": 63, "ingredients": [{"material": "chicken", "quantity": 120, "unit": "g"}]}'
Send shadow update request with order_id 63.
Send shadow update request with order_id 63.
Send shadow update request with order_id 63.
Send shadow update request with order_id 63.
Send shadow update request with order_id None.
```

## Dependencies
Python 3.8.1

Docker 19.03.5

## Setup
To run Greengrass Core via docker:
```bash
docker run --rm --init -it --name aws-iot-greengrass \
--entrypoint /greengrass-entrypoint.sh \
-v /path/to/<hash>-setup/certs:/greengrass/certs \
-v /path/to/<hash>-setup/config:/greengrass/config \
-v /path/to/logs:/greengrass/ggc/var/log \
-v /path/to/<hash>/deployment:/greengrass/ggc/deployment \
-p 8883:8883 \
amazon/aws-iot-greengrass:latest
```
`logs` and `deployment` should be empty before the first start.

In order to run KC, please type:
```bash
python kc.py  \
--endpoint <endpoint> \
--cert /path/to/<hash>-setup/certs/<hash>.cert.pem \
--key /path/to/<hash>-setup/certs/<hash>.private.key \
--root-ca /path/to/<hash>-setup/certs/root.ca.pem
```
Make sure you have `root.ca.pem` from aws site.

In a similar way you can start Robot simulator(s):
```bash
python robot.py  \
--endpoint <endpoint> \
--cert /path/to/<robot-hash>-setup/<robot-hash>.cert.pem \
--key /path/to/<robot-hash>-setup/<robot-hash>.private.key \
--root-ca /path/to/<core-hash>-setup/certs/root.ca.pem \
--thing-name <robot-thing-name>
```
`thing-name` is not ARN but the short name of the AWS IoT device.

## Useful Greengrass links
https://youtu.be/wFeoKhVg-PM?t=627

https://youtu.be/1N7Y_gxZ9Wg

https://youtu.be/FrH-EQfQkRU

[https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-mqtt.html](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-mqtt.html)

[https://github.com/aws/aws-iot-device-sdk-python-v2/tree/master/samples](https://github.com/aws/aws-iot-device-sdk-python-v2/tree/master/samples)



[schema]: docs/schema.png "SCHEMA"

from __future__ import absolute_import
from __future__ import print_function
import argparse
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
import sys
import threading
import time
import json
import random
from uuid import uuid4

parser = argparse.ArgumentParser(
    description="Kitchen coordinator simulator.")
parser.add_argument('--endpoint', required=True, help="Your AWS IoT custom endpoint, not including a port. ")
parser.add_argument(
    '--cert', help="File path to your client certificate, in PEM format.")
parser.add_argument(
    '--key', help="File path to your private key, in PEM format.")
parser.add_argument('--root-ca', help="File path to root certificate authority, in PEM format. " +
                                      "Necessary if MQTT server uses a certificate that's not already in " +
                                      "your trust store.")
parser.add_argument('--client-id', default="test-" +
                    str(uuid4()), help="Client ID for MQTT connection.")

parser.add_argument('--verbosity', choices=[x.name for x in io.LogLevel], default=io.LogLevel.NoLogs.name,
                    help='Logging level')

# Using globals to simplify sample code
args = parser.parse_args()

io.init_logging(getattr(io.LogLevel, args.verbosity), 'stderr')

terminate_script = threading.Event()

# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    print("Connection interrupted. error: {}".format(error))


# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print("Connection resumed. return_code: {} session_present: {}".format(
        return_code, session_present))

    if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
        print("Session did not persist. Resubscribing to existing topics...")
        resubscribe_future, _ = connection.resubscribe_existing_topics()

        # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
        # evaluate result with a callback instead.
        resubscribe_future.add_done_callback(on_resubscribe_complete)


def on_resubscribe_complete(resubscribe_future):
    resubscribe_results = resubscribe_future.result()
    print("Resubscribe results: {}".format(resubscribe_results))

    for topic, qos in resubscribe_results['topics']:
        if qos is None:
            sys.exit("Server rejected resubscribe to topic: {}".format(topic))


# Callback when the subscribed topic receives a message
def on_update_accepted(topic, payload, **kwargs):
    robot_state = json.loads(payload.decode("utf-8"))['state']['reported']
    thing = robot_state['thing_name']
    idle = robot_state['idle']

    print(f'Robot {thing} is idle: {idle}')

    if not idle:
        return

    robot_topic = f"robots/{thing}/process_order"
    order_id = random.randint(1, 100)

    order_info = {
      "order_id": order_id,
      'ingredients': [
        {
          'material': 'chicken',
          'quantity': 120,
          'unit': 'g'
        }
      ]
    }

    print(f'Sending next order {order_id} to the robot {thing}')

    mqtt_connection.publish(
        topic=robot_topic,
        payload=json.dumps(order_info),
        qos=mqtt.QoS.AT_MOST_ONCE)


if __name__ == '__main__':
    # Spin up resources
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=args.endpoint,
        port=8883,
        cert_filepath=args.cert,
        pri_key_filepath=args.key,
        client_bootstrap=client_bootstrap,
        ca_filepath=args.root_ca,
        on_connection_interrupted=on_connection_interrupted,
        on_connection_resumed=on_connection_resumed,
        client_id=args.client_id,
        clean_session=False,
        keep_alive_secs=6)

    print("Connecting to {} with client ID '{}'...".format(
        args.endpoint, args.client_id))

    connect_future = mqtt_connection.connect()

    # Future.result() waits until a result is available
    connect_future.result()
    print("Connected!")

    # Subscribe
    update_accepted_topic = '$aws/things/+/shadow/update/accepted'
    print("Subscribing to topic '{}'...".format(update_accepted_topic))
    subscribe_future, packet_id = mqtt_connection.subscribe(
        topic=update_accepted_topic,
        qos=mqtt.QoS.AT_MOST_ONCE,
        callback=on_update_accepted)

    subscribe_result = subscribe_future.result()
    print("Subscribed with {}".format(str(subscribe_result['qos'])))

    terminate_script.wait()

    # Disconnect
    print("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    print("Disconnected!")

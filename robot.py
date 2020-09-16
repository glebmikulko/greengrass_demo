from __future__ import absolute_import
from __future__ import print_function
import argparse
from awscrt import io, mqtt, auth, http
from awsiot import iotshadow
from awsiot import mqtt_connection_builder
import sys
import threading
import time
import json
import math
from uuid import uuid4

parser = argparse.ArgumentParser(
    description="Robot simulator.")
parser.add_argument('--endpoint', required=True, help="Your AWS IoT custom endpoint, not including a port. ")
parser.add_argument(
    '--cert', help="File path to your client certificate, in PEM format.")
parser.add_argument(
    '--key', help="File path to your private key, in PEM format.")
parser.add_argument('--root-ca', help="File path to root certificate authority, in PEM format. " +
                                      "Necessary if MQTT server uses a certificate that's not already in " +
                                      "your trust store.")
parser.add_argument('--client-id', default="test-" +
                    str(uuid4()), help="Client ID for MQTT connection. Should be equal IoT Thing name")

parser.add_argument('--thing-name', required=True, help="Thing name for the robot (should be unique).")

parser.add_argument('--verbosity', choices=[x.name for x in io.LogLevel], default=io.LogLevel.NoLogs.name,
                    help='Logging level')

# Using globals to simplify sample code
args = parser.parse_args()

io.init_logging(getattr(io.LogLevel, args.verbosity), 'stderr')

simulate_activity = threading.Event()
current_order_id = None
shadow_client = None

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
def on_order_accepted(topic, payload, **kwargs):
    print("Received message from topic '{}': {}".format(topic, payload))
    global current_order_id

    current_order_id = json.loads(payload.decode("utf-8"))['order_id']
    simulate_activity.set()


def simulate_order_processing(order_id):
    # start sending shadow updates
    # send 4 busy signals and 1 idle
    for _ in range(4):
        change_shadow_value(order_id)
        time.sleep(3)

    change_shadow_value(None)

def change_shadow_value(order_id):
    print(f"Send shadow update request with order_id {order_id}.")
    shadow = {
        'thing_name': args.thing_name,
        'idle': order_id == None,
        'order_id': order_id,
        'paused': False,
    }

    request = {
        'state': {
            'desired': shadow,
            'reported': shadow,
        }
    }

    mqtt_connection.publish(
    '$aws/things/{}/shadow/update'.format(args.thing_name),
    json.dumps(request),
    mqtt.QoS(0))

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

    shadow_client = iotshadow.IotShadowClient(mqtt_connection)

    # Future.result() waits until a result is available
    connect_future.result()
    print("Connected!")

    # Subscribe
    update_accepted_topic = f'robots/{args.thing_name}/process_order'
    print("Subscribing to topic '{}'...".format(update_accepted_topic))
    subscribe_future, packet_id = mqtt_connection.subscribe(
        topic=update_accepted_topic,
        qos=mqtt.QoS.AT_MOST_ONCE,
        callback=on_order_accepted)

    subscribe_result = subscribe_future.result()
    print("Subscribed with {}".format(str(subscribe_result['qos'])))

    # send initial state
    change_shadow_value(None)

    while(True):
        simulate_activity.wait()
        simulate_order_processing(current_order_id)
        simulate_activity.clear()

    # Disconnect
    print("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    print("Disconnected!")

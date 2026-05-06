import paho.mqtt.client as mqtt

MQTT_BROKER = "127.0.0.1"

def on_connect(client, userdata, flags, rc):
    print(f"Connected to Mosquitto. Listening for ESP32...")
    # The '#' wildcard subscribes to test/debug AND test/imu
    client.subscribe("test/#") 

def on_message(client, userdata, msg):
    # Print the topic name and the message payload
    print(f"[{msg.topic}] {msg.payload.decode()}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print("\nExiting monitor...")
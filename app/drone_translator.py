import paho.mqtt.client as mqtt
import sys

# --- Configuration ---
MQTT_BROKER = "localhost" # Assuming broker is on the same machine
MQTT_PORT = 1883
TOPIC_SUB = "fire"
TOPIC_PUB = "droneC"

# ASUS Vivobook M1502YA HD Webcam Specifications
# (Change these when moving back to the Raspberry Pi 5)
CAMERA_WIDTH = 640.0
FOV_H = 65.0 

def on_connect(client, userdata, flags, rc):
    """Callback for when the client receives a CONNACK response from the server."""
    if rc == 0:
        print(f"[*] Successfully connected to Mosquitto Broker at {MQTT_BROKER}")
        client.subscribe(TOPIC_SUB)
        print(f"[*] Subscribed to topic: '{TOPIC_SUB}'")
    else:
        print(f"[!] Failed to connect to broker, return code {rc}")

def on_disconnect(client, userdata, rc):
    """Callback for when the client disconnects from the server."""
    print("[!] Disconnected from Mosquitto Broker.")

def on_message(client, userdata, msg):
    """Callback for when a PUBLISH message is received from the server."""
    payload = msg.payload.decode()
    
    try:
        # Parse the incoming string: "x_min,y_min,x_max,y_max"
        coords = payload.split(',')
        if len(coords) != 4:
            raise ValueError("Payload does not contain exactly 4 coordinates.")
            
        x_min, x_max = float(coords[0]), float(coords[2])
        
        # 1. Calculate the center of the fire bounding box (horizontal)
        c_x = (x_min + x_max) / 2.0
        
        # 2. Calculate the offset from the center of the camera frame
        # (c_x - center) / center gives a normalized value between -1.0 (far left) and 1.0 (far right)
        normalized_x = (c_x - (CAMERA_WIDTH / 2.0)) / (CAMERA_WIDTH / 2.0)
        
        # 3. Multiply by half the Field of View to get the required yaw angle
        angle = normalized_x * (FOV_H / 2.0)
        
        # Determine direction for logging
        direction = "RIGHT" if angle > 0 else "LEFT"
        if abs(angle) < 2.0:
            direction = "CENTERED (FORWARD)"
            
        print(f"[+] Target at X: {c_x:.1f} | Calc Angle: {abs(angle):.2f}° {direction}")
        
        # Publish the target angle to the drone control topic
        client.publish(TOPIC_PUB, str(angle))
        
    except Exception as e:
        print(f"[-] Error processing message payload '{payload}': {e}")

# --- Main Execution ---
if __name__ == "__main__":
    print("Initializing Logic Controller...")
    
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except ConnectionRefusedError:
        print(f"[!] ERROR: Connection refused. Is Mosquitto running on {MQTT_BROKER}?")
        sys.exit(1)
        
    print("Waiting for fire coordinates... (Press Ctrl+C to exit)")
    
    try:
        # loop_forever() handles reconnections automatically and blocks the script 
        # so it stays alive listening for messages.
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down Logic Controller...")
        client.disconnect()
        sys.exit(0)
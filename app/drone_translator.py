import paho.mqtt.client as mqtt
import sys

MQTT_BROKER = "127.0.0.1" 
TOPIC_SUB = "tower/target_box"
TOPIC_PUB = "cmd/target_angle"

CAMERA_WIDTH = 640.0
FOV_H = 65.0 

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[TRANSLATOR] Connected to Broker at {MQTT_BROKER}")
        client.subscribe(TOPIC_SUB)
    else:
        print(f"[TRANSLATOR] Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    payload = msg.payload.decode()
    try:
        coords = payload.split(',')
        if len(coords) != 4: raise ValueError("Invalid coords.")
            
        x_min, x_max = float(coords[0]), float(coords[2])
        c_x = (x_min + x_max) / 2.0
        normalized_x = (c_x - (CAMERA_WIDTH / 2.0)) / (CAMERA_WIDTH / 2.0)
        angle = normalized_x * (FOV_H / 2.0)
        
        direction = "RIGHT" if angle > 0 else "LEFT"
        if abs(angle) < 2.0: direction = "CENTERED"
            
        print(f"[TRANSLATOR] Target X:{c_x:.1f} | Angle: {abs(angle):.2f}° {direction}")
        client.publish(TOPIC_PUB, str(angle))
        
    except Exception as e:
        print(f"[TRANSLATOR] Error processing payload: {e}")

if __name__ == "__main__":
    print("[TRANSLATOR] Initializing Logic Controller...")
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    try: client.connect(MQTT_BROKER, 1883, 60)
    except ConnectionRefusedError: sys.exit(1)
        
    print("[TRANSLATOR] Waiting for fire coordinates...")
    try: client.loop_forever()
    except KeyboardInterrupt: sys.exit(0)
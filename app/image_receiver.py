import paho.mqtt.client as mqtt
import cv2
import numpy as np
import base64
import json
from ultralytics import YOLO

MQTT_BROKER = "127.0.0.1"
model = YOLO("/home/cheetah/Documents/memoir_work/Simulation/best.pt")

def on_connect(client, userdata, flags, rc):
    print("[+] Vision Node Connected to Broker")
    client.subscribe("drone/stream/raw") 

def on_message(client, userdata, msg):
    try:
        img_data = base64.b64decode(msg.payload)
        np_arr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        h, w, _ = frame.shape

        results = model(frame, verbose=False)
        annotated_frame = results[0].plot()
        
        _, buffer = cv2.imencode('.png', annotated_frame)
        b64_img = base64.b64encode(buffer).decode('utf-8')
        client.publish("drone/stream/yolo", b64_img)

        payload = {"fire": False, "cx": -1, "cy": -1, "w": w, "h": h}

        if len(results[0].boxes) > 0:
            best_box = results[0].boxes[0]
            x1, y1, x2, y2 = best_box.xyxy[0].tolist()
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            
            payload.update({"fire": True, "cx": cx, "cy": cy})
            print(f"[VISION] Fire Detected at X:{cx} Y:{cy}")
        else:
            print("[VISION] No Fire in current frame.")

        client.publish("vision/yolo_coords", json.dumps(payload))

    except Exception as e:
        print(f"[VISION] Processing Error: {e}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, 1883, 60)

print("[VISION] Starting Edge Vision Processor...")
client.loop_forever()
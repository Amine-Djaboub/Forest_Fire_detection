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
    client.subscribe("drone/video_feed") 

def on_message(client, userdata, msg):
    try:
        # 1. Decode incoming image from drone
        img_data = base64.b64decode(msg.payload)
        np_arr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        h, w, _ = frame.shape

        # 2. Run YOLO Inference
        results = model(frame, verbose=False)
        
        # 3. Extract the image with YOLO boxes drawn on it
        annotated_frame = results[0].plot()
        
        # 4. Encode the annotated frame as a PNG and send to GCS
        _, buffer = cv2.imencode('.png', annotated_frame)
        b64_img = base64.b64encode(buffer).decode('utf-8')
        client.publish("gcs/video_feed", b64_img)

        # 5. Process telemetry for the Movement Logic script
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

        client.publish("droneCam/detection", json.dumps(payload))

    except Exception as e:
        print(f"[-] Vision Processing Error: {e}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, 1883, 60)

print("Starting Edge Vision Processor...")
client.loop_forever()
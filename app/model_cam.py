import cv2
import paho.mqtt.client as mqtt
import time
from ultralytics import YOLO
import subprocess
import os

# --- Configuration ---
SMOKE_THRESHOLD = 2600 
model = YOLO("/home/cheetah/Documents/memoir_work/Simulation/best.pt")

# State variables
t = time.time()
high_power_mode = False
gcs_launched = False

# Trigger this when fire is detected
def launch_gcs():
    global gcs_launched

    if gcs_launched:
        return
    # Use Popen so the fire script keeps running while the GUI opens
    script_path = "/Simulations/app/gcs.py"
    venv_python = "/Simulations/myvenv/bin/python3"
    
    subprocess.Popen([venv_python, script_path])
    gcs_launched = True
    print(">> Ground Control Station launched.")

def on_message(client, userdata, msg):
    if msg.topic == "node":
        try:
            smoke_level = int(msg.payload.decode())
            if smoke_level > SMOKE_THRESHOLD:
                print(f"ALARM! Smoke level {smoke_level} exceeded threshold. Waking up YOLO...")
                high_power()
        except ValueError:
            pass 

def high_power():
    global high_power_mode, t
    high_power_mode = True
    t = time.time() # Reset the timer every time this is called

def check_power():
    global high_power_mode
    time_since_highp = time.time() - t
    if time_since_highp >= 15.0:
        print("15 seconds without fire or smoke. Reverting to Low Power Mode.")
        high_power_mode = False

# Setup MQTT
client = mqtt.Client()
client.on_message = on_message
client.connect("localhost", 1883, 60)
client.subscribe("node")
client.loop_start()

# Initialize Webcam
cap = cv2.VideoCapture(0) 

print("System initialized. Waiting for sensor triggers or interval scans...")

while True:
    ret, frame = cap.read()
    if not ret: 
        print("Failed to grab frame.")
        time.sleep(1)
        continue

    # --- YOLO INFERENCE ---
    fire_detected = False
    box = [0, 0, 0, 0]

    results = model(frame, verbose=False)
    
    if len(results[0].boxes) > 0:
        fire_detected = True
        best_box = results[0].boxes[0]
        x1, y1, x2, y2 = best_box.xyxy[0].tolist()
        box = [int(x1), int(y1), int(x2), int(y2)]
        
        cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), (0, 0, 255), 2)
        cv2.putText(frame, "FIRE TARGET", (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

    cv2.imshow('Server Vision Dashboard', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

    # --- PUBLISH MQTT PAYLOAD ---
    if fire_detected:
        payload = f"{box[0]},{box[1]},{box[2]},{box[3]}"
        client.publish("fire", payload)
        print(f"Published Fire Coords: {payload}")
        high_power() # Reset the 15-second timer because we just saw a fire
        #launch_gcs()

    # --- POWER MANAGEMENT LOGIC ---
    if not high_power_mode:
        print("Sleeping for 15s to save power...")
        time.sleep(15) 
        
        for _ in range(5): 
            cap.read()
    else:
        # Check if it is time to turn off high power mode
        check_power()

cap.release()
cv2.destroyAllWindows()
client.loop_stop()
import cv2
import paho.mqtt.client as mqtt
import time
from ultralytics import YOLO

SMOKE_THRESHOLD = 2600 
model = YOLO("/home/cheetah/Documents/memoir_work/Simulation/best.pt")

t = time.time()
high_power_mode = False

def on_message(client, userdata, msg):
    if msg.topic == "sensor/smoke":
        try:
            smoke_level = int(msg.payload.decode())
            if smoke_level > SMOKE_THRESHOLD:
                print(f"[TOWER] ALARM! Smoke {smoke_level} exceeded threshold. Waking YOLO...")
                high_power()
        except ValueError: pass 

def high_power():
    global high_power_mode, t
    high_power_mode = True
    t = time.time() 

def check_power():
    global high_power_mode
    if time.time() - t >= 15.0:
        print("[TOWER] 15 seconds clear. Reverting to Low Power Mode.")
        high_power_mode = False

client = mqtt.Client()
client.on_message = on_message
client.connect("127.0.0.1", 1883, 60)
client.subscribe("sensor/smoke")
client.loop_start()

cap = cv2.VideoCapture(0) 
print("[TOWER] System initialized. Waiting for sensor triggers...")

while True:
    ret, frame = cap.read()
    if not ret: 
        time.sleep(1)
        continue

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

    if fire_detected:
        payload = f"{box[0]},{box[1]},{box[2]},{box[3]}"
        client.publish("tower/target_box", payload)
        print(f"[TOWER] Published Target Box: {payload}")
        high_power() 

    if not high_power_mode:
        print("[TOWER] Sleeping for 15s to save power...")
        time.sleep(15) 
        for _ in range(5): cap.read()
    else:
        check_power()

cap.release()
cv2.destroyAllWindows()
client.loop_stop()
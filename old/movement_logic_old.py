import paho.mqtt.client as mqtt
import json
import time
import threading

MQTT_BROKER = "127.0.0.1"
TOLERANCE = 30

class DroneLogic:
    def __init__(self):
        self.state = "STANDBY"
        self.target_angle = 0.0
        self.is_moving = False
        self.tower_fire_detected = False
        self.gyro_active = False
        
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        print("[LOGIC] Connected to Broker")
        self.client.subscribe("cmd/target_angle")              
        self.client.subscribe("telemetry/imu")              
        self.client.subscribe("vision/yolo_coords")  
        self.client.subscribe("vision/edge_coords")            

    def execute_forward_burst(self):
        self.is_moving = True
        print("[LOGIC] Emitting FORWARD for 0.5s...")
        time.sleep(0.5)
        print("[LOGIC] Emitting STOP. Waiting for next image...")
        self.is_moving = False

    def check_start_condition(self):
        if self.state == "STANDBY" and self.tower_fire_detected and self.gyro_active:
            self.state = "SEARCHING"
            print("\n[LOGIC] System Armed! Commencing search protocol.")
            self.client.publish("gcs/ui_state", json.dumps({
                "status": "SEARCHING", "dir_x": "NONE", "dir_y": "FORWARD", 
                "cx": -1, "cy": -1, "w": 160, "h": 120, "locked": False
            }))

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()

        if topic == "cmd/target_angle":
            try:
                self.target_angle = float(payload)
                self.tower_fire_detected = True
                print(f"[LOGIC] Tower Fire verified. Target Angle: {self.target_angle}")
                self.check_start_condition()
            except: pass

        elif topic == "telemetry/imu":
            if not self.gyro_active:
                self.gyro_active = True
                print("[LOGIC] Gyro telemetry established with ESP32.")
                self.check_start_condition()

        elif topic == "vision/yolo_coords":
            if self.state == "STANDBY": return 
                
            try:
                data = json.loads(payload)
                if data.get("fire"):
                    print("\n[LOGIC] YOLO DETECTED FIRE! Switching to LOCK MODE.")
                    self.state = "LOCKING"
                    self.client.publish("cmd/drone_state", "LOCK") 
                    
                    self.client.publish("gcs/ui_state", json.dumps({
                        "status": "LOCKING", "dir_x": "NONE", "dir_y": "NONE", 
                        "cx": -1, "cy": -1, "w": 160, "h": 120, "locked": False
                    }))
                else:
                    if self.is_moving: return 
                    dir_turn = "RIGHT" if self.target_angle > 0 else "LEFT"
                    print(f"[LOGIC] No Fire. Adjusting angle: {dir_turn}")
                    threading.Thread(target=self.execute_forward_burst).start()
            except: pass

        elif topic == "vision/edge_coords" and self.state == "LOCKING":
            try:
                data = json.loads(payload)
                cx, cy = data.get("cx", -1), data.get("cy", -1)
                if cx == -1: return 
                
                w, h = data.get("w", 160), data.get("h", 120)
                dx = cx - (w / 2)
                dy = cy - (h / 2)
                
                if abs(dx) < TOLERANCE and abs(dy) < TOLERANCE:
                    print("[LOGIC] FAST-LOCK ALIGNED! Ready for drop.")
                    self.client.publish("gcs/ui_state", json.dumps({"status": "LOCKED", "cx": cx, "cy": cy, "w": w, "h": h}))
                else:
                    dir_x = "RIGHT" if dx > 0 else "LEFT"
                    dir_y = "BACK" if dy > 0 else "FORWARD"
                    self.client.publish("gcs/ui_state", json.dumps({"status": "ADJUSTING", "cx": cx, "cy": cy, "w": w, "h": h}))
            except: pass

if __name__ == "__main__":
    logic = DroneLogic()
    logic.client.connect(MQTT_BROKER, 1883, 60)
    print("[LOGIC] Starting Controller (STANDBY MODE)...")
    logic.client.loop_forever()
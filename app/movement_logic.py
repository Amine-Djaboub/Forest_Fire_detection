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
        
        # System Arming Conditions
        self.tower_fire_detected = False
        self.gyro_active = False
        
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        print("[+] Movement Logic Connected")
        self.client.subscribe("droneC")              
        self.client.subscribe("droneR")              
        self.client.subscribe("droneCam/detection")  
        self.client.subscribe("droneCam")            

    def execute_forward_burst(self):
        """Runs the exact 0.5 second forward movement."""
        self.is_moving = True
        print("[LOGIC] Emitting FORWARD for 0.5s...")
        time.sleep(0.5)
        print("[LOGIC] Emitting STOP. Waiting for next image...")
        self.is_moving = False

    def check_start_condition(self):
        """Transitions to SEARCHING only when both conditions are met."""
        if self.state == "STANDBY" and self.tower_fire_detected:
            self.state = "SEARCHING"
            print("\n[LOGIC] System Armed! Commencing search protocol.")
            self.client.publish("gcs/nav_state", json.dumps({
                "status": "SEARCHING", "dir_x": "NONE", "dir_y": "FORWARD", 
                "cx": -1, "cy": -1, "w": 160, "h": 120, "locked": False
            }))

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()

        # 1. Condition 1: Tower Cam Angle
        if topic == "droneC":
            try:
                self.target_angle = float(payload)
                self.tower_fire_detected = True
                print(f"[LOGIC] Tower Cam Fire verified. Target Angle: {self.target_angle}")
                self.check_start_condition()
            except: pass

        # 2. Condition 2: Drone Telemetry Active
        elif topic == "droneR":
            if not self.gyro_active:
                self.gyro_active = True
                print("[LOGIC] Gyro telemetry established with ESP32.")
                self.check_start_condition()

        # 3. SEARCH MODE: Processing YOLO Data
        elif topic == "droneCam/detection":
            if self.state == "STANDBY": 
                return 
                
            try:
                data = json.loads(payload)
                
                if data.get("fire"):
                    # IMMEDIATE OVERRIDE - Fire Detected!
                    print("\n[!] YOLO DETECTED FIRE! Interrupting flight and switching to LOCK MODE.")
                    self.state = "LOCKING"
                    self.client.publish("drone/mode", "LOCK") 
                    
                    # Update GCS instantly to show the camera reboot phase
                    self.client.publish("gcs/nav_state", json.dumps({
                        "status": "LOCKING", "dir_x": "NONE", "dir_y": "NONE", 
                        "cx": -1, "cy": -1, "w": 160, "h": 120, "locked": False
                    }))
                else:
                    # Only ignore frames if we are actively moving AND there is no fire
                    if self.is_moving:
                        return 
                        
                    dir_turn = "RIGHT" if self.target_angle > 0 else "LEFT"
                    print(f"[LOGIC] No Fire. Adjusting angle: {dir_turn}")
                    threading.Thread(target=self.execute_forward_burst).start()
            except Exception as e:
                pass

        # 4. LOCK MODE: Processing ESP32 Fast Pixel Data
        elif topic == "droneCam" and self.state == "LOCKING":
            try:
                data = json.loads(payload)
                cx, cy = data.get("cx", -1), data.get("cy", -1)
                
                # If the ESP32 is sending blank data (-1), wait for it to see the fire
                if cx == -1: return 
                
                w, h = data.get("w", 160), data.get("h", 120)
                dx = cx - (w / 2)
                dy = cy - (h / 2)
                
                if abs(dx) < TOLERANCE and abs(dy) < TOLERANCE:
                    print("[LOGIC] FAST-LOCK ALIGNED! Ready for drop.")
                    self.client.publish("gcs/nav_state", json.dumps({"status": "LOCKED", "cx": cx, "cy": cy, "w": w, "h": h}))
                else:
                    dir_x = "RIGHT" if dx > 0 else "LEFT"
                    dir_y = "BACK" if dy > 0 else "FORWARD"
                    self.client.publish("gcs/nav_state", json.dumps({"status": "ADJUSTING", "cx": cx, "cy": cy, "w": w, "h": h}))
            except Exception as e: 
                pass

if __name__ == "__main__":
    logic = DroneLogic()
    logic.client.connect(MQTT_BROKER, 1883, 60)
    print("Starting Movement Logic Controller (STANDBY MODE)...")
    logic.client.loop_forever()
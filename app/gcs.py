import tkinter as tk
from tkinter import font
import math
import json
import paho.mqtt.client as mqtt

MQTT_BROKER = "127.0.0.1"

# Telemetry
drone_yaw = 0.0
target_yaw = 0.0
latest_frame_data = None

# UI State Dictionary (Updated by MQTT)
nav_state = {
    "status": "STANDBY",
    "dir_x": "NONE",
    "dir_y": "NONE",
    "cx": -1, "cy": -1, "w": 160, "h": 120,
    "locked": False
}

def on_connect(client, userdata, flags, rc):
    print("GCS Connected to Broker")
    client.subscribe("droneC")
    client.subscribe("droneR")
    client.subscribe("gcs/nav_state") # Listen to the logic controller
    client.subscribe("gcs/video_feed") # NEW: Listen for the video

def on_message(client, userdata, msg):
    global drone_yaw, target_yaw, nav_state, latest_frame_data
    payload = msg.payload.decode()
    
    if msg.topic == "droneC":
        try: target_yaw = float(payload)
        except: pass
    elif msg.topic == "droneR":
        try:
            data = json.loads(payload)
            drone_yaw = data['yaw'] # Read the absolute hardware angle directly
        except: pass
    elif msg.topic == "gcs/nav_state":
        try: nav_state = json.loads(payload)
        except: pass
    elif msg.topic == "gcs/video_feed": # NEW: Catch the image
        latest_frame_data = payload

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, 1883, 60)
mqtt_client.loop_start()

# ==========================================
# GUI SETUP (Same as before)
# ==========================================
root = tk.Tk()
root.title("Drone GCS - Active Mission")
# NEW: Widened the window from 1250 to 1600 to fit the video feed

root.geometry("1600x650") 
root.configure(bg="#1a1a1a")

f_btn = font.Font(family="Helvetica", size=11, weight="bold")
f_header = font.Font(family="Helvetica", size=14, weight="bold")

# --- SECTION 1: CONTROLS ---
s1 = tk.Frame(root, bg="#1a1a1a", padx=20, pady=20)
s1.pack(side=tk.LEFT, fill=tk.Y)

def send_drop():
    mqtt_client.publish("drop", "GO")
    btn_drop.config(text="DISPATCHED", bg="#004400", state=tk.DISABLED)

btn_drop = tk.Button(s1, text="DROP PAYLOAD", font=f_header, bg="gray", fg="white", 
                     state=tk.DISABLED, width=20, height=2, command=send_drop)
btn_drop.pack(pady=(0, 20))

grid = tk.Frame(s1, bg="#1a1a1a")
grid.pack()

b_p = {"font": f_btn, "width": 10, "height": 3, "bg": "#333333", "fg": "white"}
btn_turn_l = tk.Button(grid, text="Turn Left", **b_p)
btn_turn_l.grid(row=0, column=0, padx=2, pady=2)
btn_fwd = tk.Button(grid, text="Forwards", **b_p)
btn_fwd.grid(row=0, column=1, padx=2, pady=2)
btn_turn_r = tk.Button(grid, text="Turn Right", **b_p)
btn_turn_r.grid(row=0, column=2, padx=2, pady=2)
btn_left = tk.Button(grid, text="Go Left", **b_p)
btn_left.grid(row=1, column=0, padx=2, pady=2)
btn_stop = tk.Button(grid, text="STOP", **b_p)
btn_stop.grid(row=1, column=1, padx=2, pady=2) 
btn_right = tk.Button(grid, text="Go Right", **b_p)
btn_right.grid(row=1, column=2, padx=2, pady=2)
btn_up = tk.Button(grid, text="UP", **b_p)
btn_up.grid(row=2, column=0, padx=2, pady=2) 
btn_back = tk.Button(grid, text="Backwards", **b_p)
btn_back.grid(row=2, column=1, padx=2, pady=2)
btn_down = tk.Button(grid, text="Down", **b_p)
btn_down.grid(row=2, column=2, padx=2, pady=2)

nav_buttons = {"FORWARD": btn_fwd, "BACK": btn_back, "LEFT": btn_left, "RIGHT": btn_right, "STOP": btn_stop}

# --- SECTION 2: COMPASS ---
s2 = tk.Frame(root, bg="#1a1a1a", padx=20, pady=20)
s2.pack(side=tk.LEFT, fill=tk.Y)
canvas = tk.Canvas(s2, width=300, height=300, bg="#1a1a1a", highlightthickness=0)
canvas.pack()
center, r = 150, 110
canvas.create_oval(center-r, center-r, center+r, center+r, outline="#444", width=2)
t_needle = canvas.create_line(center, center, center, center, fill="white", width=3, arrow=tk.LAST)
d_needle = canvas.create_line(center, center, center, center, fill="#00AAFF", width=5, arrow=tk.LAST)

# --- SECTION 3: TARGETING RADAR ---
s3 = tk.Frame(root, bg="#1a1a1a", padx=20, pady=20)
s3.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
instr_label = tk.Label(s3, text="WAITING FOR TARGET...", font=f_header, fg="yellow", bg="#1a1a1a")
instr_label.pack(pady=10)
radar_w, radar_h = 480, 360
radar = tk.Canvas(s3, width=radar_w, height=radar_h, bg="#001100", highlightthickness=2, highlightbackground="#00FF00")
radar.pack()
radar.create_line(radar_w/2, 0, radar_w/2, radar_h, fill="#004400", dash=(4, 4))
radar.create_line(0, radar_h/2, radar_w, radar_h/2, fill="#004400", dash=(4, 4))
radar.create_oval(radar_w/2 - 20, radar_h/2 - 20, radar_w/2 + 20, radar_h/2 + 20, outline="#00FF00", width=2)
target_dot = radar.create_oval(-10, -10, -10, -10, fill="red", outline="white", width=2)

# --- NEW: SECTION 4: LIVE VIDEO FEED (Far Right) ---
s4 = tk.Frame(root, bg="#1a1a1a", padx=20, pady=20)
s4.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

video_title = tk.Label(s4, text="LIVE AI VISION (SEARCH MODE)", font=f_header, fg="white", bg="#1a1a1a")
video_title.pack(pady=10)

# 320x240 matches the QVGA resolution coming from the drone
video_label = tk.Label(s4, bg="#000000", width=320, height=240, highlightthickness=2, highlightbackground="#444444")
video_label.pack()

# ==========================================
# MASTER UI UPDATE LOOP
# ==========================================
def update_ui():
    global latest_frame_data # <--- ADDED THIS LINE
    
    # 1. Update Compass Needles
    tr, dr = math.radians(target_yaw), math.radians(drone_yaw)
    canvas.coords(t_needle, center, center, center+r*0.9*math.sin(tr), center-r*0.9*math.cos(tr))
    canvas.coords(d_needle, center, center, center+r*0.9*math.sin(dr), center-r*0.9*math.cos(dr))

    # 2. Reset Button Colors
    for btn in nav_buttons.values(): btn.config(bg="#333333")

    # 3. Apply state from movement_logic.py
    if nav_state["status"] == "STANDBY":
        instr_label.config(text="STANDBY: AWAITING TOWER & TELEMETRY", fg="gray")
        radar.coords(target_dot, -10, -10, -10, -10) 
        btn_drop.config(state=tk.DISABLED, bg="gray")

    elif nav_state["status"] == "SEARCHING": # <--- CHANGED TO elif
        instr_label.config(text="SEARCHING: MOVING FORWARD", fg="orange")
        radar.coords(target_dot, -10, -10, -10, -10) 
        btn_drop.config(state=tk.DISABLED, bg="gray")
        nav_buttons["FORWARD"].config(bg="#FF8800")


    elif nav_state["status"] == "LOCKING":
        instr_label.config(text="REBOOTING SENSOR FOR EDGE-VISION...", fg="cyan")
        radar.coords(target_dot, -10, -10, -10, -10)
        btn_drop.config(state=tk.DISABLED, bg="gray")

    elif nav_state["status"] == "LOCKED":
        instr_label.config(text="TARGET LOCKED", fg="#00FF00")
        gui_x = nav_state["cx"] * (radar_w / nav_state["w"])
        gui_y = nav_state["cy"] * (radar_h / nav_state["h"])
        radar.coords(target_dot, gui_x - 10, gui_y - 10, gui_x + 10, gui_y + 10)
        nav_buttons["STOP"].config(bg="#AA0000")
        btn_drop.config(state=tk.NORMAL, bg="#AA0000")

    elif nav_state["status"] == "ADJUSTING":
        instr_label.config(text=f"ADJUST: {nav_state['dir_y']} & {nav_state['dir_x']}", fg="yellow")
        gui_x = nav_state["cx"] * (radar_w / nav_state["w"])
        gui_y = nav_state["cy"] * (radar_h / nav_state["h"])
        radar.coords(target_dot, gui_x - 10, gui_y - 10, gui_x + 10, gui_y + 10)
        btn_drop.config(state=tk.DISABLED, bg="gray")
        
        # Highlight required buttons
        if nav_state["dir_y"] in nav_buttons: nav_buttons[nav_state["dir_y"]].config(bg="#FF8800")
        if nav_state["dir_x"] in nav_buttons: nav_buttons[nav_state["dir_x"]].config(bg="#FF8800")

    # 4. NEW: Update the Video Feed
    if latest_frame_data:
        try:
            # Tkinter's PhotoImage natively supports base64 PNG data!
            img = tk.PhotoImage(data=latest_frame_data)
            video_label.config(image=img)
            video_label.image = img # Must keep a reference so garbage collector doesn't delete it
            latest_frame_data = None # Clear it until the next frame arrives
        except Exception as e:
            pass

    # Visual cue that the feed is locked/frozen
    if nav_state["status"] in ["LOCKING", "LOCKED", "ADJUSTING"]:
        video_title.config(text="EDGE-VISION ACTIVE (FEED FROZEN)", fg="red")
        video_label.config(highlightbackground="red")
    else:
        video_title.config(text="LIVE AI VISION (SEARCH MODE)", fg="white")
        video_label.config(highlightbackground="#444444")

    root.after(50, update_ui)


update_ui()
root.mainloop()
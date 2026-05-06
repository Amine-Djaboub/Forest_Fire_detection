import tkinter as tk
import math
import json
import paho.mqtt.client as mqtt

MQTT_BROKER = "127.0.0.1"
drone_yaw = 0.0

def on_connect(client, userdata, flags, rc):
    print("Connected. Listening to test/imu...")
    client.subscribe("test/imu")

def on_message(client, userdata, msg):
    global drone_yaw
    try:
        data = json.loads(msg.payload.decode())
        drone_yaw = float(data['yaw'])
    except Exception as e:
        pass

mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, 1883, 60)
mqtt_client.loop_start()

root = tk.Tk()
root.title("Unit Test: Compass")
root.geometry("400x400")
root.configure(bg="#1a1a1a")

canvas = tk.Canvas(root, width=300, height=300, bg="#1a1a1a", highlightthickness=0)
canvas.pack(pady=30)
center, r = 150, 110
canvas.create_oval(center-r, center-r, center+r, center+r, outline="#444", width=2)
d_needle = canvas.create_line(center, center, center, center, fill="#00AAFF", width=5, arrow=tk.LAST)
yaw_label = tk.Label(root, text="YAW: 0.00°", font=("Helvetica", 16, "bold"), fg="white", bg="#1a1a1a")
yaw_label.pack()

def update_ui():
    dr = math.radians(drone_yaw)
    canvas.coords(d_needle, center, center, center+r*0.9*math.sin(dr), center-r*0.9*math.cos(dr))
    yaw_label.config(text=f"YAW: {drone_yaw:.2f}°")
    root.after(50, update_ui)

update_ui()
root.mainloop()
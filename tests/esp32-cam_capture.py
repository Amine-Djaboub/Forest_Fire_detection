import cv2

# Replace this with the IP address printed in your Arduino Serial Monitor
ESP32_URL = "http://10.121.137.60" 

print(f"Connecting to ESP32-CAM at {ESP32_URL}...")

# OpenCV natively understands MJPEG streams over HTTP!
cap = cv2.VideoCapture(ESP32_URL)

if not cap.isOpened():
    print("Cannot open stream. Check the IP address and make sure the ESP32 is running.")
    exit()

print("Stream connected! Press 'q' to quit.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame. Stream might have dropped.")
        break

    cv2.imshow('ESP32-CAM Live Feed', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
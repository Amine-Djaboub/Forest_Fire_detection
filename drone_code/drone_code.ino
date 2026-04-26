#include <WiFi.h>
#include <PubSubClient.h>
#include "esp_camera.h"
#include <Wire.h>
#include <ESP32Servo.h>
#include <base64.h> 

// ==========================================
// 1. SETTINGS & NETWORK
// ==========================================
const char* ssid = "Amine's OPPO A74";
const char* password = "amine123";
const char* mqtt_server = "10.121.137.7"; 

WiFiClient espClient;
PubSubClient client(espClient);

// ==========================================
// 2. HARDWARE DEFINITIONS
// ==========================================
#define SDA_PIN 15
#define SCL_PIN 14
#define SERVO_PIN 13
const int i2c_addr = 0x69; 

// Camera Pins omitted for brevity (Keep your standard Y2-Y9, PCLK, etc. definitions here)
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

Servo dropServo;

// ==========================================
// 3. STATE MACHINE
// ==========================================
enum SystemState { LISTEN_MODE, SEARCH_MODE, LOCK_MODE };
SystemState currentState = LISTEN_MODE;// --- 1. IMU TELEMETRY (10Hz) ---
    if (now - lastTelemetryTime >= telemetryInterval) {
      lastTelemetryTime = now;
      
      // Using your exact original working I2C requests
      Wire.beginTransmission(i2c_addr);
      Wire.write(0x0C); 
…        float ay = rawAy / 16384.0;
        float az = rawAz / 16384.0;

        String payload = "{\"ax\":" + String(ax, 2) + ",\"ay\":" + String(ay, 2) + ",\"az\":" + String(az, 2) + 
                         ",\"gx\":" + String(gx, 2) + ",\"gy\":" + String(gy, 2) + ",\"gz\":" + String(gz, 2) + 
                         ",\"yaw\":" + String(absolute_yaw, 2) + "}";
        
        client.publish("droneR", payload.c_str());
      }
    }

float absolute_yaw = 0.0;
unsigned long lastGyroMicros = 0;

unsigned long lastTelemetryTime = 0;
const long telemetryInterval = 100; // 10Hz

unsigned long lastVideoTime = 0;
const long videoInterval = 250; // 4Hz YOLO Stream

unsigned long lastLockTime = 0;
const long lockInterval = 50; // Max 20 FPS for Edge Vision to protect Wi-Fi

bool pendingCameraSwitch = false; // Safely flags the hardware reboot


void sendDebug(String msg) {
  if (client.connected()) client.publish("debug", msg.c_str());
  Serial.println(msg); 
}

// ==========================================
// 4. CAMERA SWITCHING LOGIC
// ==========================================
void initCamera(bool forYOLO) {
  esp_camera_deinit(); // Tear down any existing camera configuration
  delay(200); // Give hardware a moment

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM; config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM; config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM; config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM; config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM; config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM; config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM; config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM; config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;

  if (forYOLO) {
    config.pixel_format = PIXFORMAT_JPEG; 
    config.frame_size = FRAMESIZE_QVGA;   
    config.jpeg_quality = 12;             
    config.fb_count = 2;
  } else {
    config.pixel_format = PIXFORMAT_GRAYSCALE; 
    config.frame_size = FRAMESIZE_QQVGA;       
    config.jpeg_quality = 12;
    config.fb_count = 2;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    sendDebug("[Hardware] Camera Init Failed!");
    return;
  }

  sensor_t * s = esp_camera_sensor_get();
  if (!forYOLO && s) {
    // Lock exposure for Edge Vision
    s->set_exposure_ctrl(s, 0); 
    s->set_aec_value(s, 150);   
    sendDebug("[System] Camera in Grayscale/Low-Exposure (LOCK MODE).");
  } else {
    sendDebug("[System] Camera in Color/Auto-Exposure (SEARCH MODE).");
  }
}

// ==========================================
// 5. I2C & MQTT CALLBACKS
// ==========================================
// (Keep your initBMI160() and writeBMIRegister() functions here exactly as they were)
void writeBMIRegister(byte reg, byte value) {
  Wire.beginTransmission(i2c_addr);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

void initBMI160() {
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000); 
  delay(100);
  writeBMIRegister(0x7E, 0xB6); delay(100);
  writeBMIRegister(0x7E, 0x11); delay(100);
  writeBMIRegister(0x7E, 0x15); delay(100);
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String topicStr = String(topic);
  String msg = "";
  for (int i = 0; i < length; i++) msg += (char)payload[i];
  
  if (topicStr == "droneC" && currentState == LISTEN_MODE) {
    sendDebug("[System] Tower Cam coordinates received. Starting SEARCH_MODE.");
    currentState = SEARCH_MODE;
    client.unsubscribe("droneC");
    client.subscribe("drop");
    client.subscribe("drone/mode"); 
  } 
  else if (topicStr == "drone/mode" && msg == "LOCK" && currentState == SEARCH_MODE) {
    sendDebug("[System] Server spotted fire! Queuing camera reboot...");
    currentState = LOCK_MODE;
    pendingCameraSwitch = true; // <-- SAFE FLAG INSTEAD OF BLOCKING CALL
  }
  else if (topicStr == "drop" && currentState == LOCK_MODE) {
    sendDebug("[System] DROP COMMAND RECEIVED! Releasing payload.");
    dropServo.write(90); 
  }
}

void reconnect() {
  while (!client.connected()) {
    if (client.connect("DronePayloadESP32")) {
      client.subscribe("droneC");
      client.subscribe("drop");
      client.subscribe("drone/mode");
    } else delay(5000);
  }
}

// ==========================================
// 6. SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  
  client.setServer(mqtt_server, 1883);
  client.setBufferSize(20480); 
  client.setCallback(mqttCallback);
  reconnect();

  ESP32PWM::allocateTimer(0);
  dropServo.setPeriodHertz(50);
  dropServo.attach(SERVO_PIN, 500, 2400);
  dropServo.write(0);

  initBMI160();
  initCamera(true); // Boot up in Color/YOLO mode by default

  sendDebug("[System] Boot complete. LISTEN_MODE.");
}

// ==========================================
// 7. LOOP
// ==========================================
void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  // --- SAFE HARDWARE REBOOT ---
  if (pendingCameraSwitch) {
    pendingCameraSwitch = false;
    initCamera(false); 
  }

  if (currentState == SEARCH_MODE || currentState == LOCK_MODE) {
    unsigned long now = millis();
    
    // --- 1. IMU TELEMETRY (10Hz) ---
    if (now - lastTelemetryTime >= telemetryInterval) {
      lastTelemetryTime = now;
      
      Wire.beginTransmission(i2c_addr);
      Wire.write(0x0C); 
      byte i2c_err = Wire.endTransmission(false); 
      
      if (i2c_err != 0) {
        // If the I2C bus crashes, this tells us immediately
        Serial.println("[Hardware] I2C Error Code: " + String(i2c_err)); 
      } else {
        uint8_t bytesReceived = Wire.requestFrom((uint16_t)i2c_addr, (uint8_t)12, (uint8_t)true);
        
        if (bytesReceived == 12) {
          int16_t rawGx = Wire.read() | (Wire.read() << 8);
          int16_t rawGy = Wire.read() | (Wire.read() << 8);
          int16_t rawGz = Wire.read() | (Wire.read() << 8);
          int16_t rawAx = Wire.read() | (Wire.read() << 8);
          int16_t rawAy = Wire.read() | (Wire.read() << 8);
          int16_t rawAz = Wire.read() | (Wire.read() << 8);

          // --- THE NEW PRECISION YAW MATH ---
          unsigned long currentMicros = micros();
          float dt = (currentMicros - lastGyroMicros) / 1000000.0;
          lastGyroMicros = currentMicros;

          // Apply BMI160 2000dps scale factor (16.4) instead of radians
          float gx = rawGx / 16.4;
          float gy = rawGy / 16.4;
          float gz = rawGz / 16.4;

          // Deadband filter: ignore micro-vibrations so the compass doesn't drift
          if (abs(gz) < 1.5) gz = 0.0;

          // Accumulate exact absolute yaw
          absolute_yaw += (gz * dt);
          // ----------------------------------

          float ax = rawAx / 16384.0;
          float ay = rawAy / 16384.0;
          float az = rawAz / 16384.0;

          // Added "yaw" to the end of your JSON payload
          String payload = "{\"ax\":" + String(ax, 2) + ",\"ay\":" + String(ay, 2) + ",\"az\":" + String(az, 2) + 
                           ",\"gx\":" + String(gx, 2) + ",\"gy\":" + String(gy, 2) + ",\"gz\":" + String(gz, 2) + 
                           ",\"yaw\":" + String(absolute_yaw, 2) + "}";
          
          client.publish("droneR", payload.c_str());
        } else {
          Serial.println("[Hardware] IMU read failed. Expected 12 bytes, got: " + String(bytesReceived));
        }
      }
    }

    // --- 2. SEARCH MODE: STREAM TO YOLO (4Hz) ---
    if (currentState == SEARCH_MODE && (now - lastVideoTime >= videoInterval)) {
      lastVideoTime = now;
      camera_fb_t * fb = esp_camera_fb_get();
      if (fb) {
        String encodedString = base64::encode(fb->buf, fb->len);
        client.publish("drone/video_feed", encodedString.c_str());
        esp_camera_fb_return(fb); 
      }
    }

    // --- 3. LOCK MODE: FAST PIXEL MATH (Capped at 20Hz) ---
    if (currentState == LOCK_MODE && (now - lastLockTime >= lockInterval)) {
      lastLockTime = now;
      camera_fb_t * fb = esp_camera_fb_get();
      
      if (fb) {
        long sumX = 0, sumY = 0, count = 0;
        for (int y = 0; y < fb->height; y++) {
          for (int x = 0; x < fb->width; x++) {
            if (fb->buf[y * fb->width + x] > 240) { 
              sumX += x; sumY += y; count++;
            }
          }
        }

        String targetPayload;
        if (count > 5) { 
          targetPayload = "{\"cx\":" + String(sumX/count) + ",\"cy\":" + String(sumY/count) + 
                          ",\"w\":" + String(fb->width) + ",\"h\":" + String(fb->height) + "}";
        } else {
          targetPayload = "{\"cx\":-1,\"cy\":-1}"; 
        }
        client.publish("droneCam", targetPayload.c_str());
        esp_camera_fb_return(fb); 
      }
    }
  }
}
#include <WiFi.h>
#include <PubSubClient.h>
#include "esp_camera.h"
#include <Wire.h>
#include <ESP32Servo.h>
#include <base64.h> 

const char* ssid = "Amine's OPPO A74";
const char* password = "amine123";
const char* mqtt_server = "10.121.137.7"; 

WiFiClient espClient;
PubSubClient client(espClient);

#define SDA_PIN 15
#define SCL_PIN 14
#define SERVO_PIN 13
const int i2c_addr = 0x69; 

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

enum SystemState { LISTEN_MODE, SEARCH_MODE, LOCK_MODE };
volatile SystemState currentState = LISTEN_MODE;
volatile bool pendingCameraSwitch = false; 

// --- DUAL CORE SHARED VARIABLES ---
portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
volatile float absolute_yaw = 0.0;
volatile float shared_ax = 0, shared_ay = 0, shared_az = 0;
volatile float shared_gx = 0, shared_gy = 0, shared_gz = 0;

unsigned long lastTelemetryTime = 0;
const long telemetryInterval = 100; // Publish at 10Hz

unsigned long lastVideoTime = 0;
const long videoInterval = 500; // 2 FPS to reduce lag

unsigned long lastLockTime = 0;
const long lockInterval = 50; // Edge vision at 20 FPS

TaskHandle_t NetworkTask;

bool camInitialized = false;

void sendDebug(String msg) {
  if (client.connected()) client.publish("telemetry/debug", msg.c_str());
  Serial.println(msg); 
}

void initCamera(bool forYOLO) {
  if (camInitialized) {
    esp_camera_deinit(); 
    delay(200); 
  }

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
    sendDebug("[DRONE] Camera Init Failed!");
    return;
  }
  
  camInitialized = true; // Mark as successfully booted

  sensor_t * s = esp_camera_sensor_get();
  if (!forYOLO && s) {
    s->set_exposure_ctrl(s, 0); 
    s->set_aec_value(s, 150);   
    sendDebug("[DRONE] Camera in Grayscale/Low-Exposure (LOCK MODE).");
  } else {
    sendDebug("[DRONE] Camera in Color/Auto-Exposure (SEARCH MODE).");
  }
}

void writeBMIRegister(byte reg, byte value) {
  Wire.beginTransmission(i2c_addr);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

void initBMI160() {
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000); // Fast I2C speed
  delay(100);
  writeBMIRegister(0x7E, 0xB6); delay(100); 
  writeBMIRegister(0x7E, 0x11); delay(100); 
  writeBMIRegister(0x7E, 0x15); delay(100); 
  
  // Lock resolution to 2000dps to match the math
  writeBMIRegister(0x43, 0x28); delay(50); 
  writeBMIRegister(0x44, 0x00); delay(50); 
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String topicStr = String(topic);
  String msg = "";
  for (int i = 0; i < length; i++) msg += (char)payload[i];
  
  if (topicStr == "cmd/target_angle" && currentState == LISTEN_MODE) {
    sendDebug("[DRONE] Tower Angle received. Starting SEARCH_MODE.");
    currentState = SEARCH_MODE;
    client.unsubscribe("cmd/target_angle");
    client.subscribe("cmd/payload_drop");
    client.subscribe("cmd/drone_state"); 
  } 
  else if (topicStr == "cmd/drone_state" && msg == "LOCK" && currentState == SEARCH_MODE) {
    sendDebug("[DRONE] Server spotted fire! Queuing camera reboot...");
    currentState = LOCK_MODE;
    pendingCameraSwitch = true; 
  }
  else if (topicStr == "cmd/payload_drop" && currentState == LOCK_MODE) {
    sendDebug("[DRONE] DROP COMMAND RECEIVED! Releasing payload.");
    dropServo.write(90); 
  }
}

void reconnect() {
  while (!client.connected()) {
    if (client.connect("DronePayloadESP32")) {
      client.subscribe("cmd/target_angle");
      client.subscribe("cmd/payload_drop");
      client.subscribe("cmd/drone_state");
    } else delay(5000);
  }
}

// ==========================================
// CORE 0: NETWORK & CAMERA TASK
// ==========================================
void networkCameraTask(void * pvParameters) {
  for (;;) {
    if (!client.connected()) reconnect();
    client.loop();

    if (pendingCameraSwitch) {
      pendingCameraSwitch = false;
      initCamera(false); 
    }

    if (currentState == SEARCH_MODE || currentState == LOCK_MODE) {
      unsigned long now = millis();
      
      // 1. Publish Telemetry at 10Hz (Reading from Core 1 variables)
      if (now - lastTelemetryTime >= telemetryInterval) {
        lastTelemetryTime = now;
        
        portENTER_CRITICAL(&mux);
        float ax = shared_ax, ay = shared_ay, az = shared_az;
        float gx = shared_gx, gy = shared_gy, gz = shared_gz;
        float yaw = absolute_yaw;
        portEXIT_CRITICAL(&mux);

        String payload = "{\"ax\":" + String(ax, 2) + ",\"ay\":" + String(ay, 2) + ",\"az\":" + String(az, 2) + 
                         ",\"gx\":" + String(gx, 2) + ",\"gy\":" + String(gy, 2) + ",\"gz\":" + String(gz, 2) + 
                         ",\"yaw\":" + String(yaw, 2) + "}";
        
        client.publish("telemetry/imu", payload.c_str());
      }

      // 2. SEARCH MODE: Stream JPEG at 2 FPS
      if (currentState == SEARCH_MODE && (now - lastVideoTime >= videoInterval)) {
        lastVideoTime = now;
        camera_fb_t * fb = esp_camera_fb_get();
        if (fb) {
          String encodedString = base64::encode(fb->buf, fb->len);
          client.publish("drone/stream/raw", encodedString.c_str());
          esp_camera_fb_return(fb); 
        }
      }

      // 3. LOCK MODE: Edge Vision Math at 20 FPS
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
          client.publish("vision/edge_coords", targetPayload.c_str());
          esp_camera_fb_return(fb); 
        }
      }
    }
    // Yield to let Wi-Fi run
    vTaskDelay(10 / portTICK_PERIOD_MS); 
  }
}

// ==========================================
// SETUP
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
  initCamera(true); 

  // Pin the Heavy Networking/Camera task to Core 0
  xTaskCreatePinnedToCore(
    networkCameraTask, "NetCamTask", 10000, NULL, 1, &NetworkTask, 0
  );

  sendDebug("[DRONE] Boot complete. LISTEN_MODE.");
}

// ==========================================
// CORE 1: FAST HARDWARE LOOP
// ==========================================
unsigned long lastGyroMicros = 0;
unsigned long lastImuRead = 0;

void loop() {
  unsigned long now = micros();
  
  // Read IMU at a rock-solid 100Hz (every 10,000 microseconds)
  if (now - lastImuRead >= 10000) {
    lastImuRead = now;

    if (currentState == SEARCH_MODE || currentState == LOCK_MODE) {
      Wire.beginTransmission(i2c_addr);
      Wire.write(0x0C); 
      if (Wire.endTransmission(false) == 0) {
        
        // Inline check for the 12 bytes
        if (Wire.requestFrom((uint16_t)i2c_addr, (uint8_t)12, (uint8_t)true) == 12) {
          int16_t rawGx = Wire.read() | (Wire.read() << 8);
          int16_t rawGy = Wire.read() | (Wire.read() << 8);
          int16_t rawGz = Wire.read() | (Wire.read() << 8);
          int16_t rawAx = Wire.read() | (Wire.read() << 8);
          int16_t rawAy = Wire.read() | (Wire.read() << 8);
          int16_t rawAz = Wire.read() | (Wire.read() << 8);

          // --- THE WATCHDOG ---
          // If the sensor browns out, it spits out exact zeros.
          if (rawGx == 0 && rawGy == 0 && rawGz == 0 && rawAx == 0) {
            // Silently reboot the BMI160 sensor to recover the I2C bus
            initBMI160(); 
          } else {
            // --- NORMAL MATH ---
            unsigned long currentMicros = micros();
            float dt = (currentMicros - lastGyroMicros) / 1000000.0;
            lastGyroMicros = currentMicros;

            float gz = rawGz / 16.4; 
            if (abs(gz) < 1.5) gz = 0.0; 

            // Update shared variables safely so Core 0 can publish them
            portENTER_CRITICAL(&mux);
            absolute_yaw += (gz * dt); // Math fixed for upside down
            shared_gx = gz; shared_gy = rawGy/16.4; shared_gz = gz; 
            shared_ax = rawAx/16384.0; shared_ay = rawAy/16384.0; shared_az = rawAz/16384.0;
            portEXIT_CRITICAL(&mux);
          }
        }
      }
    }
  }
}
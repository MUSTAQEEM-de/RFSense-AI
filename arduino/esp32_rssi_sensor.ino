#include <WiFi.h>

const char* ssid = "YOUR_WIFI_NAME";
const char* password = "YOUR_WIFI_PASSWORD";

or

void setup() {
  Serial.begin(115200);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  Serial.println("Connecting...");

  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }

  Serial.println("\nConnected!");
}

void loop() {
  int rssi = WiFi.RSSI();

  // 🔥 ADD SMALL VARIATION (important for responsiveness)
  int noise = random(-2, 3);   // simulate fluctuation
  rssi += noise;

  Serial.print("RSSI:");
  Serial.println(rssi);

  delay(50);   // 🔥 FAST UPDATE (20 readings/sec)
}
/*
  Mine Rescue Rover - ESP32 Receiver
  -----------------------------------
  Reads one JSON line at a time from the Nano over UART2 and parses it
  with ArduinoJson. Prints the parsed values to the USB Serial Monitor
  for now - replace the TODO section in loop() with whatever you want
  to do with the data next (send over WiFi/LoRa, log it, act on it, etc).

  Library needed (install via Library Manager):
    - "ArduinoJson" by Benoit Blanchon (install the 6.x or 7.x version)

  Wiring from Nano (SoftwareSerial on A2/A3):
    Nano A3 (TX)  --[voltage divider, 5V->3.3V]-->  ESP32 GPIO16 (RX2)
    Nano A2 (RX)  <----------------------------------  ESP32 GPIO17 (TX2)
    Nano GND      -------------------------------------  ESP32 GND

  IMPORTANT: Nano's TX is 5V logic. ESP32 RX pins are NOT 5V tolerant.
  Use the voltage divider (or a logic-level shifter) on that line as
  discussed before wiring this up - don't connect it directly.
*/

#include <ArduinoJson.h>

#define ESP_RX2  16   // ESP32 receives here <- Nano TX (through the divider)
#define ESP_TX2  17   // ESP32 transmits here -> Nano RX

HardwareSerial nanoSerial(2);   // use UART2

void setup() {
  Serial.begin(9600);                              // USB - Serial Monitor
  nanoSerial.begin(9600, SERIAL_8N1, ESP_RX2, ESP_TX2);  // link to the Nano

  Serial.println("ESP32 ready, waiting for sensor data from Nano...");
}

void loop() {
  if (!nanoSerial.available()) {
    return;
  }

  String line = nanoSerial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) {
    return;
  }

  StaticJsonDocument<200> doc;
  DeserializationError err = deserializeJson(doc, line);

  if (err) {
    Serial.print("JSON parse failed: ");
    Serial.println(err.c_str());
    Serial.print("Raw line was: ");
    Serial.println(line);
    return;
  }

  int   mq4      = doc["mq4"];
  int   mq7      = doc["mq7"];
  float temp     = doc["temp"]     | NAN;   // default NAN if field is null/missing
  float hum      = doc["hum"]      | NAN;
  float pressure = doc["pressure"] | NAN;
  float alt      = doc["alt"]      | NAN;
  bool  bmpOk    = doc["bmp_ok"];

  // ---------- TODO: do something with the data here ----------
  // e.g. forward over WiFi/MQTT, log to SD, trigger an alert, etc.

  // For now, just print what was received:
  Serial.println("---- received from Nano ----");
  Serial.print("MQ4 raw:      "); Serial.println(mq4);
  Serial.print("MQ7 raw:      "); Serial.println(mq7);
  Serial.print("Temp:         "); Serial.println(isnan(temp) ? "n/a" : String(temp) + " C");
  Serial.print("Humidity:     "); Serial.println(isnan(hum) ? "n/a" : String(hum) + " %");
  Serial.print("BMP180:       ");
  if (!bmpOk) {
    Serial.println("not detected on Nano side");
  } else {
    Serial.println(String(pressure) + " Pa, alt " + String(alt) + " m");
  }
  Serial.println();
}

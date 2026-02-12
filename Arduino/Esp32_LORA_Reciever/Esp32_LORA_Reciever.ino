#include <DHT.h>
#include <DHT_U.h>

#include <SPI.h>
#include <LoRa.h>

//define the pins used by the transceiver module
#define ss 5
#define rst 14
#define dio0 2

#define DHTPIN  13          
#define DHTTYPE DHT11    
DHT dht(DHTPIN, DHTTYPE);

unsigned long lastDHT = 0;
const unsigned long dhtInterval = 1000;  


void setup() {
  delay(1000);
  //initialize Serial Monitor
  Serial.begin(115200);

  pinMode(DHTPIN, INPUT);
  dht.begin();

  while (!Serial);
  Serial.println("LoRa Receiver");

  //setup LoRa transceiver module
  LoRa.setPins(ss, rst, dio0);
  
  //replace the LoRa.begin(---E-) argument with your location's frequency 
  //433E6 for Asia
  //868E6 for Europe
  //915E6 for North America
  while (!LoRa.begin(433E6)) {
    Serial.println(".");
    delay(500);
  }
   // Change sync word (0xF3) to match the receiver
  // The sync word assures you don't get LoRa messages from other LoRa transceivers
  // ranges from 0-0xFF
  LoRa.setSyncWord(0x6C);
  Serial.println("LoRa Initializing OK!");
}

void loop() {
  unsigned long now = millis();

  // --- NON-BLOCKING DHT READ ---
  if (now - lastDHT >= dhtInterval) {
    lastDHT = now;

    float h = dht.readHumidity();
    float t = dht.readTemperature();

    if (isnan(h) || isnan(t)) {
      Serial.println("DHT read failed");
    } else {
      Serial.printf("T: %.1f C  H: %.1f %%\n", t, h);
    }
  }

  // try to parse packet
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    // received a packet
    Serial.print("Received packet '");

    // read packet
    while (LoRa.available()) {
      String LoRaData = LoRa.readString();
      Serial.print(LoRaData); 
    }

    // print RSSI of packet
    Serial.print("' with RSSI ");
    Serial.println(LoRa.packetRssi());
  }
}
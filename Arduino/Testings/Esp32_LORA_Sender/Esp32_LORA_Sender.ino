#include <SPI.h>
#include <LoRa.h>

//define the pins used by the transceiver module
#define LORA_SCK   14
#define LORA_MISO  2
#define LORA_MOSI  15
#define LORA_SS    13
#define LORA_RST   12
#define LORA_DIO0  4

int counter = 0;

void setup() {
  delay(1000);
  //initialize Serial Monitor
  Serial.begin(115200);
  while (!Serial);
  Serial.println("LoRa Sender");
  
  // Setup SPI pins
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI);

  // Setup LoRa module pins
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);

  
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
  Serial.print("Sending packet: ");
  Serial.println(counter);

  //Send LoRa packet to receiver
  LoRa.beginPacket();
  LoRa.print("hello ");
  LoRa.print(counter);
  LoRa.endPacket();

  counter++;

  delay(10000);
}
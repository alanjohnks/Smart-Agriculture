#include <TensorFlowLite_ESP32.h>
#include "esp_camera.h"
#include "board_config.h"
#include "esp_heap_caps.h"

// -------- TensorFlow Lite Micro Includes ----------
#include "tensorflow/lite/micro/all_ops_resolver.h"
#include "tensorflow/lite/micro/micro_error_reporter.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "tensorflow/lite/micro/system_setup.h"

#include "model.h"  // your plant_disease_mobilenetv2_int83_tflite[]

// ------------ MODEL INPUT SIZE ----------------
#define IMG_WIDTH 96
#define IMG_HEIGHT 96
#define IMG_CHANNELS 3
// ------------------------------------------------

// CLASS LABELS
const char* CLASS_NAMES[7] = {
"healthy",
"insect_pest",
"leaf_spot",
"mosaic_virus",
"small_leaf",
"white_mold",
"wilt"
};

namespace {
tflite::ErrorReporter* error_reporter = nullptr;
const tflite::Model* model = nullptr;
tflite::MicroInterpreter* interpreter = nullptr;
TfLiteTensor* input = nullptr;
TfLiteTensor* output = nullptr;

// Use PSRAM for Tensor arena
constexpr int kTensorArenaSize = 2 * 1024 * 1024;  // 2 MB
uint8_t* tensor_arena = nullptr;
}

// Convert RGB565 → RGB888
void convert_rgb565_to_rgb888(uint8_t* dest, uint16_t* src) {
for (int i = 0; i < IMG_WIDTH * IMG_HEIGHT; i++) {
uint16_t pixel = src[i];
uint8_t r = ((pixel >> 11) & 0x1F) << 3;
uint8_t g = ((pixel >> 5) & 0x3F) << 2;
uint8_t b = (pixel & 0x1F) << 3;
dest[3 * i + 0] = r;
dest[3 * i + 1] = g;
dest[3 * i + 2] = b;
}
}

void setup() {
Serial.begin(115200);
Serial.println("\nStarting ESP32-CAM + TinyML...");

// -------------- Camera Setup ----------------
camera_config_t config;
config.ledc_channel = LEDC_CHANNEL_0;
config.ledc_timer = LEDC_TIMER_0;
config.pin_d0 = Y2_GPIO_NUM;
config.pin_d1 = Y3_GPIO_NUM;
config.pin_d2 = Y4_GPIO_NUM;
config.pin_d3 = Y5_GPIO_NUM;
config.pin_d4 = Y6_GPIO_NUM;
config.pin_d5 = Y7_GPIO_NUM;
config.pin_d6 = Y8_GPIO_NUM;
config.pin_d7 = Y9_GPIO_NUM;
config.pin_xclk = XCLK_GPIO_NUM;
config.pin_pclk = PCLK_GPIO_NUM;
config.pin_vsync = VSYNC_GPIO_NUM;
config.pin_href = HREF_GPIO_NUM;
config.pin_sccb_sda = SIOD_GPIO_NUM;
config.pin_sccb_scl = SIOC_GPIO_NUM;
config.pin_pwdn = PWDN_GPIO_NUM;
config.pin_reset = RESET_GPIO_NUM;

config.xclk_freq_hz = 20000000;
config.frame_size = FRAMESIZE_96X96;
config.pixel_format = PIXFORMAT_RGB565;
config.fb_count = 1;

if (esp_camera_init(&config) != ESP_OK) {
Serial.println("Camera init failed!");
return;
}
Serial.println("Camera OK");

// -------------- TensorFlow Lite Setup ----------------
// Allocate Tensor arena in PSRAM
tensor_arena = (uint8_t*) heap_caps_malloc(kTensorArenaSize, MALLOC_CAP_SPIRAM);
if (!tensor_arena) {
Serial.println("Failed to allocate tensor arena in PSRAM!");
return;
}
Serial.println("Tensor arena allocated in PSRAM.");

static tflite::MicroErrorReporter micro_error_reporter;
error_reporter = &micro_error_reporter;

model = tflite::GetModel(plant_disease_mobilenetv2_int83_tflite);
if (model->version() != TFLITE_SCHEMA_VERSION) {
Serial.println("Model schema mismatch");
return;
}

static tflite::AllOpsResolver resolver;
static tflite::MicroInterpreter static_interpreter(
model, resolver, tensor_arena, kTensorArenaSize, error_reporter);

interpreter = &static_interpreter;

if (interpreter->AllocateTensors() != kTfLiteOk) {
Serial.println("AllocateTensors failed");
return;
}

input = interpreter->input(0);
output = interpreter->output(0);

Serial.println("TinyML Ready!");
}

void loop() {
camera_fb_t* fb = esp_camera_fb_get();
if (!fb) {
Serial.println("Camera Capture Failed");
return;
}

Serial.println("\nImage Captured!");

// Convert RGB565 → RGB888 (into model input buffer)
uint16_t* src565 = (uint16_t*)fb->buf;
uint8_t* model_input = input->data.uint8;

convert_rgb565_to_rgb888(model_input, src565);

esp_camera_fb_return(fb);

// -------- Run inference ----------
if (interpreter->Invoke() != kTfLiteOk) {
Serial.println("Inference failed!");
return;
}

// ----- Read all 7 class probabilities -----
float max_score = -1;
int max_class = -1;

Serial.println("Class probabilities:");

for (int i = 0; i < 7; i++) {
uint8_t q = output->data.uint8[i];
float prob = q * output->params.scale;  // scale=0.00390625


Serial.printf("%d: %s → %.4f\n", i, CLASS_NAMES[i], prob);

if (prob > max_score) {
  max_score = prob;
  max_class = i;
}


}

// -------- Final predicted class --------
Serial.printf("\nFINAL RESULT → %s (%.4f)\n",
CLASS_NAMES[max_class], max_score);

Serial.println("------------------------------------");

delay(1500);
}

#include <Arduino.h>
#include <esp_camera.h>
#include <esp_heap_caps.h>
#include <TensorFlowLite_ESP32.h>
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_error_reporter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "model_data.h"
#include "test_patch.h"

alignas(16) static uint8_t arena[96*1024];
tflite::MicroInterpreter* engine;
bool camera_ok=false;
float last_score=-1;
uint32_t last_inference_us=0;
void infer(const char* mode) {
  uint32_t start=micros();
  if(engine->Invoke()!=kTfLiteOk){Serial.println("Invoke failed");return;}
  auto o=engine->output(0);
  float score=(o->data.int8[1]-o->params.zero_point)*o->params.scale;
  last_score=score;last_inference_us=micros()-start;
  Serial.printf("%s defect=%.5f inference_us=%lu free_heap=%u min_heap=%u\n",mode,score,(unsigned long)(micros()-start),ESP.getFreeHeap(),ESP.getMinFreeHeap());
}
void setup(){
  Serial.begin(115200); delay(3000);
  static tflite::MicroMutableOpResolver<5> ops;
  ops.AddConv2D();ops.AddMaxPool2D();ops.AddMean();ops.AddFullyConnected();ops.AddSoftmax();
  const tflite::Model* model=tflite::GetModel(model_data);
  if(model->version()!=TFLITE_SCHEMA_VERSION){Serial.println("Schema mismatch");return;}
  static tflite::MicroErrorReporter reporter;
  static tflite::MicroInterpreter interpreter(model,ops,arena,sizeof(arena),&reporter);
  engine=&interpreter;
  if(engine->AllocateTensors()!=kTfLiteOk){Serial.println("Allocation failed");engine=nullptr;return;}
  memcpy(engine->input(0)->data.int8,test_patch,sizeof(test_patch));infer("stored_test");
  camera_config_t c={};
  c.pin_pwdn=-1;c.pin_reset=-1;c.pin_xclk=10;c.pin_sccb_sda=40;c.pin_sccb_scl=39;
  c.pin_d0=15;c.pin_d1=17;c.pin_d2=18;c.pin_d3=16;c.pin_d4=14;c.pin_d5=12;c.pin_d6=11;c.pin_d7=48;
  c.pin_vsync=38;c.pin_href=47;c.pin_pclk=13;c.xclk_freq_hz=20000000;
  c.ledc_timer=LEDC_TIMER_0;c.ledc_channel=LEDC_CHANNEL_0;
  c.pixel_format=PIXFORMAT_GRAYSCALE;c.frame_size=FRAMESIZE_QVGA;
  c.fb_location=CAMERA_FB_IN_PSRAM;c.fb_count=1;c.grab_mode=CAMERA_GRAB_WHEN_EMPTY;
  camera_ok=esp_camera_init(&c)==ESP_OK;
  Serial.println(camera_ok?"Camera ready: center 64x64 crop":"Camera failed; stored inference still available. Check Sense expansion/sensor.");
}
void loop(){
  if(!engine){delay(1000);return;}
  if(!camera_ok){delay(3000);memcpy(engine->input(0)->data.int8,test_patch,sizeof(test_patch));infer("stored_test");return;}
  uint32_t start=micros(); auto fb=esp_camera_fb_get();
  if(!fb){Serial.println("Capture failed");delay(1000);return;}
  if(fb->format!=PIXFORMAT_GRAYSCALE || fb->width<64 || fb->height<64){esp_camera_fb_return(fb);delay(1000);return;}
  auto in=engine->input(0);int left=(fb->width-64)/2,top=(fb->height-64)/2;
  for(int y=0;y<32;y++)for(int x=0;x<32;x++){
    float v=fb->buf[(top+2*y+1)*fb->width+left+2*x+1]/255.0f;
    int q=lroundf(v/in->params.scale)+in->params.zero_point;
    in->data.int8[y*32+x]=(int8_t)constrain(q,-128,127);
  }
  last_score=-1;infer("camera");
  bool preview=false;
  while(Serial.available()){if(Serial.read()=='V')preview=true;}
  if(preview){
    Serial.printf("FRAME %u %u %u %.6f %lu\n",(unsigned)fb->width,(unsigned)fb->height,(unsigned)fb->len,last_score,(unsigned long)last_inference_us);
    Serial.write(fb->buf,fb->len);Serial.write('\n');Serial.flush();
  }
  esp_camera_fb_return(fb);
  Serial.printf("capture_to_result_us=%lu\n",(unsigned long)(micros()-start));delay(1000);
}

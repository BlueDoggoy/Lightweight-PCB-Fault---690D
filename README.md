# DeepPCB baseline for XIAO ESP32-S3 Sense

## Live USB camera viewer
Run `./view-camera.ps1 -Port COM6` to open the desktop preview. Close any serial
monitor first; only one program can use the port at a time. The viewer shows the
full grayscale frame, the inspected central 64x64 region, the 32x32 model input,
and the score from that same frame. The square is the inspected region, not a
predicted defect bounding box. USB transfer adds preview latency; displayed
inference timing excludes that transfer. Close the viewer before flashing again.
The updated firmware sends raw frames only when requested by the viewer.

Research prototype: binary classification of a centered 64x64 grayscale PCB crop,
resized to 32x32 with nearest-neighbor sampling. It does not locate defects or
classify the six defect types. Training uses annotated defects and non-overlapping
background crops from tested images (not templates), avoiding template-vs-test
image shortcuts. Official test images remain held out; validation is selected
from training images before cropping. Related board layouts can still occur
across official splits, so these are not unseen-board generalization results.

## Train
For a fresh checkout, install Python 3.12 and Git, then run:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
git clone https://github.com/tangsanli5201/DeepPCB.git data/DeepPCB
git -C data/DeepPCB checkout 08e98c4db5922613fb97176eb3d6497d48260cb1
```

The trained model and merged firmware are included, so retraining is optional.

Python 3.12, TensorFlow 2.18, Pillow, NumPy. Run from this directory:

```powershell
.venv/Scripts/python.exe train.py
```

Outputs: `artifacts/weights.npz`, `architecture.json`, `pcb_int8.tflite`, `metrics.json`, split manifest,
and firmware headers. The TFLite file alone is NOT flashable firmware.

## Build and flash
Use `./build.ps1` to compile on Windows: the GCC toolchain needs a short path
without spaces, so this script temporarily maps P: to the project.
Once the merged binary exists, `./flash.ps1 -Port COM5` flashes it at address zero.

Requires the XIAO ESP32-S3 **Sense camera expansion** with standard Seeed pins.
An externally wired camera needs a different pin mapping. PSRAM must be present.

```powershell
$env:PLATFORMIO_CORE_DIR="$PWD\.platformio"
.venv/Scripts/python.exe -m platformio run -d firmware
.venv/Scripts/python.exe -m platformio run -d firmware -t upload --upload-port COM5
.venv/Scripts/python.exe -m platformio device monitor --port COM5 --baud 115200
```

Replace COM5 with the actual port. Upload overwrites existing application firmware.
PlatformIO uploads the application, partition table and bootloader at appropriate
offsets; do not flash the application binary alone at address zero.

At startup, compare `stored_test defect=` against `artifacts/device_test.json`.
Then point the camera at a well-lit, sharply focused PCB region. Only the central
64x64 pixels are evaluated, once per second. Match the defect scale in the
training data. A score >=0.5 is the initial defect threshold, not a calibrated
probability. Real-camera accuracy is unmeasured until labeled device captures
are evaluated. Camera failure leaves the stored-input test operational.

Serial output reports inference and capture-to-result times plus free/minimum
heap. Minimum heap is not a complete memory benchmark: also report static arena,
firmware size, PSRAM and camera buffers separately for the project.

## Sources
- Dataset: https://github.com/tangsanli5201/DeepPCB (README restricts research use).
- Camera pins: https://wiki.seeedstudio.com/xiao_esp32s3_camera_usage/
- Inference library: https://github.com/tanakamasayuki/Arduino_TensorFlowLite_ESP32

This baseline uses post-training int8 quantization. The later NAS contribution
and required course comparisons/ablations are not implemented here.

## Initial measured results
DeepPCB revision: `08e98c4db5922613fb97176eb3d6497d48260cb1`.
6,280 sampled patches from the official test split: float accuracy 90.80%;
int8 accuracy 90.27%, defect recall 98.22%, false positive rate 17.68%.
Model: 3,602 parameters, 8,288-byte TFLite file. Accuracy decreases 0.53 percentage
points after quantization. These are desktop inference results, not device measurements.
This initial model favors recall and produces substantial false alarms.

On the connected XIAO ESP32-S3, camera inference was approximately 287 ms per
patch. USB preview and camera capture also ran successfully. These checks verify
execution, not reliable fault recognition on arbitrary camera images. The current
model is trained on bare-board trace defects; populated boards and images of
screens are outside the validated distribution. It does not identify defect type.

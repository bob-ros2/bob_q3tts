# bob_q3tts

A ROS 2 wrapper for the **Qwen3-TTS** model, providing high-fidelity, low-latency text-to-speech with streaming aggregation and voice cloning capabilities. It also includes a Qt-based GUI for real-time parameter tuning.

## Quick Start

1. **Launch the TTS Service**:
   ```bash
   ros2 run bob_q3tts tts
   ```

2. **Open the Parameter GUI**:
   ```bash
   ros2 run bob_q3tts gui
   ```

### Docker Usage

#### Using Docker Compose (Recommended)
```bash
docker-compose build
docker-compose up
```

#### Using Docker CLI
1. **Build the Image**:
   ```bash
   docker build -t bob_q3tts .
   ```

2. **Run the Node** (with GPU and Audio):
   ```bash
   docker run -it --rm \
     --gpus all \
     --device /dev/snd \
     -e Q3TTS_MODEL_DIR=/models \
     -e ROS_DOMAIN_ID=99 \
     -v  /blue/dev/q3tts/models:/models \
     --network host \
     --ipc host \
     bob-q3tts:latest
   ```

## Troubleshooting Audio

If you hear no sound or see "Invalid sample rate" errors (common with HDMI/GPU audio):

1. **List Devices** (inside container):
   ```bash
   python3 -c "import sounddevice as sd; print(sd.query_devices())"
   ```
2. **Set Device**: Find the index or name (e.g., `HDA NVidia: HDMI 0 (hw:2,3)`) and set the `audio_device` parameter.
3. **Force Resampling**: If your hardware only supports 48kHz, set `target_sample_rate` to `48000`.

Example:
```bash
ros2 param set /tts audio_device "HDA NVidia: HDMI 0 (hw:2,3)"
ros2 param set /tts target_sample_rate 48000
```

## ROS API

### Topics

| Name | Type | Direction | Description |
| :--- | :--- | :--- | :--- |
| `text` | `std_msgs/String` | Subscriber | Incoming text. Aggregated and synthesized at sentence boundaries. |
| `spoken_text` | `std_msgs/String` | Publisher | The text currently being spoken. Published right before playback. |

---

### Parameters

The node uses static configuration for initialization and dynamic parameters for per-sentence tuning.

#### Core Configuration (Static)
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `model_id` | `string` | The Hugging Face model ID. Env: `Q3TTS_MODEL_ID` (Default: `Qwen/Qwen3-TTS-12Hz-1.7B-Base`) |
| `model_dir` | `string` | Local directory for model caching. Env: `Q3TTS_MODEL_DIR` (Default: `./models`) |
| `sentence_delimiters` | `string_array` | Characters that trigger synthesis. Env: `Q3TTS_SENTENCE_DELIMITERS` (Default: `[",", ".", ":", ";", "!", "?"]`) |
| `flush_timeout` | `integer` | Timeout in ms to flush buffer without delimiter. Env: `Q3TTS_FLUSH_TIMEOUT` (Default: `700`) |

#### Generation Settings (Dynamic)
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `language` | `string` | Speech language. Env: `Q3TTS_LANGUAGE` (Default: `auto`) |
| `do_sample` | `bool` | Enable sampling for Stage 1. Env: `Q3TTS_DO_SAMPLE` (Default: `true`) |
| `temperature` | `double` | Sampling temperature for Stage 1. Env: `Q3TTS_TEMPERATURE` (Default: `0.9`) |
| `top_p` | `double` | Nucleus sampling threshold. Env: `Q3TTS_TOP_P` (Default: `1.0`) |
| `top_k` | `integer` | Top-k sampling limit. Env: `Q3TTS_TOP_K` (Default: `50`) |
| `repetition_penalty` | `double` | Penalty for repeated sounds. Env: `Q3TTS_REPETITION_PENALTY` (Default: `1.05`) |

#### Subtalker Settings (Dynamic)
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `subtalker_dosample` | `bool` | Enable sampling for Stage 2. Env: `Q3TTS_SUBTALKER_DOSAMPLE` (Default: `true`) |
| `subtalker_temperature`| `double` | Temperature for acoustic texture. Env: `Q3TTS_SUBTALKER_TEMPERATURE` (Default: `0.9`) |
| `subtalker_top_p` | `double` | Nucleus sampling for Stage 2. Env: `Q3TTS_SUBTALKER_TOP_P` (Default: `1.0`) |
| `subtalker_top_k` | `integer` | Top-k for Stage 2. Env: `Q3TTS_TOP_K` (Default: `50`) |

#### Voice Clone / ICL (Dynamic)
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `voice_ref_audio` | `string` | Path to reference `.wav`. Env: `Q3TTS_VOICE_REF_AUDIO` (Default: `<pkg_share>/config/eva_24khz.wav`) |
| `voice_ref_text` | `string` | Transcript or path to transcript file. Reading from file enables dynamic updates. Env: `Q3TTS_VOICE_REF_TEXT` (Default: `<pkg_share>/config/voice_ref_text.txt`) |

#### Output & Storage (Dynamic)
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `play` | `bool` | Enable/disable audio playback. Env: `Q3TTS_PLAY` (Default: `true`) |
| `player` | `string` | Player: `sys` (native) or executable path. Env: `Q3TTS_PLAYER` (Default: `sys`) |
| `audio_device` | `string` | Device ID or name for sounddevice. Env: `Q3TTS_AUDIO_DEVICE` (Default: `""`) |
| `file_prefix` | `string` | Prefix for saving audio files. Env: `Q3TTS_FILE_PREFIX` (Default: `""`) |
| `file_start_index` | `integer` | Starting index for file naming. Env: `Q3TTS_FILE_START_INDEX` (Default: `1`) |

# ROS Package [bob_q3tts](https://github.com/bob-ros2/bob_q3tts)

[![Docker Build and Push](https://github.com/bob-ros2/bob_q3tts/actions/workflows/docker-image.yml/badge.svg)](https://github.com/bob-ros2/bob_q3tts/actions/workflows/docker-image.yml)
[![ROS 2 CI](https://github.com/bob-ros2/bob_q3tts/actions/workflows/ros-ci.yml/badge.svg)](https://github.com/bob-ros2/bob_q3tts/actions/workflows/ros-ci.yml)

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

The package is automatically built and pushed to the GitHub Container Registry (GHCR).

#### Using the Pre-built Image
```bash
docker pull ghcr.io/bob-ros2/bob-q3tts:latest
```

#### Using Docker Compose (Recommended)
```bash
docker-compose build
docker-compose up
```

#### Using Docker CLI
1. **Build the Image** (locally):
   ```bash
   docker build -t bob-q3tts .
   ```

2. **Run the Node** (with GPU and Audio):
   ```bash
   docker run -it --rm \
     --gpus all \
     --device /dev/snd \
     -e Q3TTS_MODEL_DIR=/models \
     -e ROS_DOMAIN_ID=99 \
     -v $(pwd)/models:/models \
     --network host \
     --ipc host \
     ghcr.io/bob-ros2/bob-q3tts:latest
   ```


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
| `sentence_delimiters` | `string_array` | Characters or strings that trigger synthesis (e.g. `[". ", "! ", "? "]`). Use `[""]` or empty list `[]` to disable splitting. Env: `Q3TTS_SENTENCE_DELIMITERS` (Default: `[""]`) |
| `flush_timeout` | `integer` | Timeout in ms to flush buffer without delimiter. Env: `Q3TTS_FLUSH_TIMEOUT` (Default: `700`) |
| `substitute` | `string_array` | Regex-based [pattern, replacement] pairs for text cleaning (HTML, emojis, etc.). Use `[""]` for no replacement. Env: `Q3TTS_SUBSTITUTE` (Default: `[""]`) |

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
| `control_instructions` | `string` | Instructions to dynamically shape voice without audio samples. **Note:** If defined, it actively overrides voice-cloning via `voice_ref_audio`! Env: `Q3TTS_CONTROL_INSTRUCTIONS` (Default: `""`) |
| `voice_ref_audio` | `string` | Path to reference `.wav`. Env: `Q3TTS_VOICE_REF_AUDIO` (Default: `<pkg_share>/config/eva_24khz.wav`) |
| `voice_ref_text` | `string` | Transcript or path to transcript file. Reading from file enables dynamic updates. Env: `Q3TTS_VOICE_REF_TEXT` (Default: `<pkg_share>/config/voice_ref_text.txt`) |

#### Output & Storage (Dynamic)
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `play` | `bool` | Enable/disable audio playback. Env: `Q3TTS_PLAY` (Default: `true`) |
| `player` | `string` | Player: `sys` (native) or executable path. Env: `Q3TTS_PLAYER` (Default: `sys`) |
| `audio_device` | `string` | Device ID or name for sounddevice. Env: `Q3TTS_AUDIO_DEVICE` (Default: `""`) |
| `target_sample_rate` | `integer` | Force resampling for local playback (0 = auto). Env: `Q3TTS_TARGET_SAMPLE_RATE` (Default: `0`) |
| `file_prefix` | `string` | Prefix for saving audio files. Env: `Q3TTS_FILE_PREFIX` (Default: `""`) |
| `file_start_index` | `integer` | Starting index for file naming. Env: `Q3TTS_FILE_START_INDEX` (Default: `1`) |

## Audio Architecture & Sample Rates

The node handles different sample rates for local playback and remote streaming:

- **Local Playback (`target_sample_rate` = 0)**: 
  - The model generates audio at **24,000 Hz**.
  - If the soundcard (e.g., HDMI) doesn't support 24kHz, the node automatically falls back to **48,000 Hz** resampling.
  - This fallback becomes "sticky" (remembered) to ensure zero-latency for subsequent sentences.
- **Remote Streaming (`audio_raw` topic)**:
  - Audio published to the ROS topic is **always fixed at 44,100 Hz**.
  - This ensure compatibility with standard streaming tools and bridges (like Twitch bots) that expect a constant frequency.

## Troubleshooting Audio

If you hear no sound or see "Invalid sample rate" errors (common with HDMI/GPU audio), or experience **ALSA underrun** messages:

1. **Use aplay fallback**: Set the parameter `player:=aplay`. This bypasses the Python-native sound library and uses the more robust system utility to stream the audio data.
2. **List Devices** (inside container):
   ```bash
   python3 -c "import sounddevice as sd; print(sd.query_devices())"
   ```
3. **Set Device**: Find the index or name (e.g., `HDA NVidia: HDMI 0 (hw:2,3)`) and set the `audio_device` parameter.
4. **Automatic Handling**: By default (`target_sample_rate: 0`), the node will try to auto-detect a working rate (falling back to 48kHz). You only need to manually set `target_sample_rate` if the auto-detection fails or you have very specific hardware needs.

### Text Cleaning Example

The `substitute` parameter is designed to remove "garbage" characters that common LLMs might stream (like HTML leftovers or emojis) which cannot be spoken by a TTS model.

```yaml
# Example launch snippet
ros2 run bob_q3tts tts --ros-args -p 'substitute:=[
  "&nbsp;","",   # Remove non-breaking spaces
  "<br>"," ",     # Replace <br> with space
  "[\\U00010000-\\U0010ffff\\u2600-\\u27BF\\ufe00-\\ufe0f]","", # Remove emojis/icons
  "https?://\\S+","", # Remove URLs
  "[*~_|<>\\^`\\]\\[]"," ", # Remove markdown formatting chars
  "\\s{2,}"," " # Normalize multiple spaces
]'
```

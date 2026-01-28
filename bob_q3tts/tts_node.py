# Copyright 2026 Bob Ros
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import queue
import subprocess
import tempfile
import threading
import time

from ament_index_python.packages import get_package_share_directory
from rcl_interfaces.msg import ParameterDescriptor
from rcl_interfaces.msg import ParameterType
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class TTSnode(Node):
    """ROS node that provides an interface to Qwen3-TTS with streaming text aggregation."""

    def __init__(self):
        super().__init__('tts')

        # Get package share directory for defaults
        try:
            package_share = get_package_share_directory('bob_q3tts')
        except Exception:
            package_share = ''

        # 1. ROS Parameters - Core
        self.declare_parameter(
            'model_id',
            os.environ.get('Q3TTS_MODEL_ID', 'Qwen/Qwen3-TTS-12Hz-1.7B-Base'),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='The model id of the Qwen3-TTS model to use.'
            )
        )
        self.declare_parameter(
            'model_dir',
            os.environ.get('Q3TTS_MODEL_DIR', os.path.join(os.getcwd(), 'models')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Local directory where models are stored/cached.'
            )
        )
        self.declare_parameter(
            'language',
            os.environ.get('Q3TTS_LANGUAGE', 'auto'),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Speech language (e.g. English, German, auto).'
            )
        )
        self.declare_parameter(
            'sentence_delimiters',
            os.environ.get('Q3TTS_SENTENCE_DELIMITERS', ',.:;!?').split(',')
            if 'Q3TTS_SENTENCE_DELIMITERS' in os.environ
            else [',', '.', ':', ';', '!', '?'],
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING_ARRAY,
                description='Delimiters that trigger sentence aggregation.'
            )
        )
        self.declare_parameter(
            'flush_timeout',
            int(os.environ.get('Q3TTS_FLUSH_TIMEOUT', '700')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_INTEGER,
                description='Timeout in ms to flush the text buffer without a delimiter.'
            )
        )

        # 1. ROS Parameters - Generation (First Stage)
        self.declare_parameter(
            'do_sample',
            os.environ.get('Q3TTS_DO_SAMPLE', 'true').lower() == 'true',
            ParameterDescriptor(
                type=ParameterType.PARAMETER_BOOL,
                description='Whether to use sampling for the first stage.'
            )
        )
        self.declare_parameter(
            'temperature',
            float(os.environ.get('Q3TTS_TEMPERATURE', '0.9')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Sampling temperature for the first stage.'
            )
        )
        self.declare_parameter(
            'top_p',
            float(os.environ.get('Q3TTS_TOP_P', '1.0')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Top-p sampling for the first stage.'
            )
        )
        self.declare_parameter(
            'top_k',
            int(os.environ.get('Q3TTS_TOP_K', '50')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_INTEGER,
                description='Top-k sampling for the first stage.'
            )
        )
        self.declare_parameter(
            'repetition_penalty',
            float(os.environ.get('Q3TTS_REPETITION_PENALTY', '1.05')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Repetition penalty.'
            )
        )

        # 1. ROS Parameters - Subtalker Generation (Second Stage)
        self.declare_parameter(
            'subtalker_dosample',
            os.environ.get('Q3TTS_SUBTALKER_DOSAMPLE', 'true').lower() == 'true',
            ParameterDescriptor(
                type=ParameterType.PARAMETER_BOOL,
                description='Whether to use sampling for the second stage.'
            )
        )
        self.declare_parameter(
            'subtalker_temperature',
            float(os.environ.get('Q3TTS_SUBTALKER_TEMPERATURE', '0.9')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Sampling temperature for the second stage.'
            )
        )
        self.declare_parameter(
            'subtalker_top_p',
            float(os.environ.get('Q3TTS_SUBTALKER_TOP_P', '1.0')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_DOUBLE,
                description='Top-p sampling for the second stage.'
            )
        )
        self.declare_parameter(
            'subtalker_top_k',
            int(os.environ.get('Q3TTS_TOP_K', '50')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_INTEGER,
                description='Top-k sampling for the second stage.'
            )
        )

        # 1. ROS Parameters - Voice Clone / ICL
        self.declare_parameter(
            'voice_ref_audio',
            os.environ.get(
                'Q3TTS_VOICE_REF_AUDIO',
                os.path.join(package_share, 'config', 'eva_24khz.wav')
            ),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Reference audio file for voice cloning.'
            )
        )
        self.declare_parameter(
            'voice_ref_text',
            os.environ.get(
                'Q3TTS_VOICE_REF_TEXT',
                os.path.join(package_share, 'config', 'voice_ref_text.txt')
            ),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Transcript or path to transcript text for reference audio.'
            )
        )

        # 1. ROS Parameters - Output
        self.declare_parameter(
            'play',
            os.environ.get('Q3TTS_PLAY', 'true').lower() == 'true',
            ParameterDescriptor(
                type=ParameterType.PARAMETER_BOOL,
                description='Whether to play the audio immediately.'
            )
        )
        self.declare_parameter(
            'player',
            os.environ.get('Q3TTS_PLAYER', 'sys'),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Audio player: "sys" or executable path (e.g. aplay).'
            )
        )
        self.declare_parameter(
            'file_prefix',
            os.environ.get('Q3TTS_FILE_PREFIX', ''),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_STRING,
                description='Prefix for saved audio files.'
            )
        )
        self.declare_parameter(
            'file_start_index',
            int(os.environ.get('Q3TTS_FILE_START_INDEX', '1')),
            ParameterDescriptor(
                type=ParameterType.PARAMETER_INTEGER,
                description='Starting index for saved audio files.'
            )
        )

        # 2. State & Queues
        self.text_buffer = ""
        self.last_text_time = self.get_clock().now()
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        self.lock = threading.Lock()
        self.file_index = self.get_parameter('file_start_index').value

        # 3. Subscriber & Publisher
        self.sub = self.create_subscription(
            String,
            'text',
            self.text_callback,
            1000
        )
        self.pub = self.create_publisher(
            String,
            'spoken_text',
            10
        )

        # 4. Initialization & Threading
        self.model = None
        self.sd = None
        self.sf = None
        self.torch = None
        self.get_logger().info("Loading Qwen3-TTS libraries and model...")

        try:
            # Set environment variables before model loading
            model_dir = self.get_parameter('model_dir').value
            os.environ["HF_HOME"] = model_dir
            os.environ["HUGGINGFACE_HUB_CACHE"] = model_dir

            # Import heavy libraries inside __init__
            import torch
            from qwen_tts import Qwen3TTSModel
            self.torch = torch

            # Try importing sounddevice for native playback
            try:
                import sounddevice as sd
                self.sd = sd
            except ImportError:
                self.sd = None

            self.model = Qwen3TTSModel.from_pretrained(
                self.get_parameter('model_id').value,
                device_map="cuda:0",
                dtype=torch.bfloat16,
                attn_implementation="flash_attention_2",
                cache_dir=model_dir
            )

            # Validate language
            requested_lang = self.get_parameter('language').value
            supported_langs = self.model.get_supported_languages()
            if requested_lang.lower() != 'auto':
                if not any(lang.lower() == requested_lang.lower() for lang in supported_langs):
                    self.get_logger().error(
                        f"Unsupported language: '{requested_lang}'. Supported: {supported_langs}"
                    )
                    return

            self.get_logger().info("Model loaded successfully.")

        except Exception as e:
            self.get_logger().error(f"Failed to initialize TTS node: {e}")
            return

        self.tts_thread = threading.Thread(target=self.tts_loop, daemon=True)
        self.audio_thread = threading.Thread(target=self.audio_loop, daemon=True)

        self.tts_thread.start()
        self.audio_thread.start()

        # Timer to flush buffer
        self.flush_timer = self.create_timer(0.1, self.flush_timer_callback)

        self.get_logger().info("TTS Node ready and listening on topic 'text'.")

    def _get_sf(self):
        """Lazy load soundfile library."""
        if self.sf is None:
            try:
                import soundfile as sf
                self.sf = sf
            except ImportError as e:
                self.get_logger().error(f"Failed to import soundfile: {e}")
                raise e
        return self.sf

    def text_callback(self, msg):
        """Aggregate incoming words/text into sentences based on delimiters."""
        delimiters = self.get_parameter('sentence_delimiters').value
        input_text = msg.data

        with self.lock:
            self.last_text_time = self.get_clock().now()
            for char in input_text:
                self.text_buffer += char
                if char in delimiters:
                    sentence = self.text_buffer.strip()
                    if sentence:
                        self.get_logger().info(f"Aggregated sentence: '{sentence}'")
                        self.text_queue.put(sentence)
                    self.text_buffer = ""

    def flush_timer_callback(self):
        """Flush the text buffer if the timeout has passed."""
        timeout_ms = self.get_parameter('flush_timeout').value
        if timeout_ms <= 0:
            return

        with self.lock:
            if not self.text_buffer:
                return

            now = self.get_clock().now()
            diff = (now - self.last_text_time).nanoseconds / 1e6
            if diff > timeout_ms:
                sentence = self.text_buffer.strip()
                if sentence:
                    self.get_logger().info(f"Flushing buffer due to timeout: '{sentence}'")
                    self.text_queue.put(sentence)
                self.text_buffer = ""

    def tts_loop(self):
        """Process the text queue and generate audio."""
        while rclpy.ok():
            try:
                # Wait for text with a timeout to allow checking rclpy.ok()
                text = self.text_queue.get(timeout=1.0)

                # Resolve parameters per-request to enable live tuning
                ref_audio = self.get_parameter('voice_ref_audio').value
                ref_text_param = self.get_parameter('voice_ref_text').value
                language = self.get_parameter('language').value

                # Resolve ref_text if it's a file path
                ref_text = ref_text_param
                if ref_text and (os.path.isfile(ref_text) or ref_text.startswith('/')):
                    try:
                        if os.path.isfile(ref_text):
                            with open(ref_text, 'r') as f:
                                ref_text = f.read().strip()
                    except Exception as e:
                        self.get_logger().error(f"Failed to read ref_text {ref_text_param}: {e}")
                        ref_text = ""

                self.get_logger().info(f"Generating audio for: '{text}' (Language: {language})")
                start_time = time.time()

                # Build voice clone prompt mode
                # x_vector_only_mode=True if ref_text is empty, otherwise icl_mode=True
                x_vector_mode = True if not ref_text else False

                # Generate audio
                wavs, sr = self.model.generate_voice_clone(
                    text=text,
                    language=language,
                    ref_audio=ref_audio,
                    ref_text=ref_text if ref_text else None,
                    x_vector_only_mode=x_vector_mode,
                    do_sample=self.get_parameter('do_sample').value,
                    temperature=self.get_parameter('temperature').value,
                    top_p=self.get_parameter('top_p').value,
                    top_k=self.get_parameter('top_k').value,
                    repetition_penalty=self.get_parameter('repetition_penalty').value,
                    subtalker_dosample=self.get_parameter('subtalker_dosample').value,
                    subtalker_temperature=self.get_parameter('subtalker_temperature').value,
                    subtalker_top_p=self.get_parameter('subtalker_top_p').value,
                    subtalker_top_k=self.get_parameter('subtalker_top_k').value
                )

                latency = time.time() - start_time
                self.get_logger().info(f"Generated audio in {latency:.2f}s")

                # Push to audio queue (with text for feedback)
                self.audio_queue.put((wavs[0], sr, text))

                # Cleanup cache
                if self.torch and self.torch.cuda.is_available():
                    self.torch.cuda.empty_cache()

                self.text_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                self.get_logger().error(f"Error in TTS loop: {e}")

    def audio_loop(self):
        """Consume the audio queue for playback and storage."""
        while rclpy.ok():
            try:
                audio_data, sr, spoken_text = self.audio_queue.get(timeout=1.0)

                # 1. Save to file if prefix is provided
                file_prefix = self.get_parameter('file_prefix').value
                if file_prefix:
                    filename = f"{file_prefix}_{self.file_index:05d}.wav"
                    self._get_sf().write(filename, audio_data, sr)
                    self.get_logger().info(f"Saved audio to {filename}")
                    self.file_index += 1

                # 2. Publish text before starting playback
                msg = String()
                msg.data = spoken_text
                self.pub.publish(msg)
                self.get_logger().info(f"Speaking: '{spoken_text}'")

                # 3. Play if enabled
                if self.get_parameter('play').value:
                    self.play_audio(audio_data, sr)

                self.audio_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                self.get_logger().error(f"Error in audio loop: {e}")

    def play_audio(self, audio_data, sr):
        """Play audio using native library or configured executable."""
        player = self.get_parameter('player').value

        if player == 'sys':
            # Use Python-native library (sounddevice)
            if self.sd is not None:
                try:
                    # sounddevice.play is non-blocking, we use wait() to simulate blocking
                    # as requested by the original design (serial processing)
                    self.sd.play(audio_data, sr)
                    self.sd.wait()
                except Exception as e:
                    self.get_logger().warn(f"Native playback failed: {e}. Falling back to aplay.")
                    self._play_with_executable('aplay', audio_data, sr)
            else:
                self.get_logger().warn("sounddevice not installed. Falling back to aplay.")
                self._play_with_executable('aplay', audio_data, sr)
        else:
            # Use configured external player
            self._play_with_executable(player, audio_data, sr)

    def _play_with_executable(self, executable, audio_data, sr):
        """Play audio using an external command."""
        temp_file_path = None
        try:
            # Use a standard python library for cross-platform temporary files
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as ntf:
                temp_file_path = ntf.name

            # Write audio to the temporary file
            self._get_sf().write(temp_file_path, audio_data, sr)

            # Run the external player
            subprocess.run(
                [executable, temp_file_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            self.get_logger().error(f"Playback with {executable} failed: {e}")
        finally:
            # Clean up the temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception as e:
                    self.get_logger().warn(f"Failed to remove temp file {temp_file_path}: {e}")


def main(args=None):
    rclpy.init(args=args)
    node = TTSnode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Shutting down node...")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

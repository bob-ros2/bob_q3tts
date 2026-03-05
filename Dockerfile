# ARG ROS_DISTRO is used to select the base ROS 2 image
ARG ROS_DISTRO=humble
FROM ros:${ROS_DISTRO}-ros-base

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies for audio, GPU, and building Python packages
RUN apt-get update && apt-get install -y \
    python3-pip \
    libasound2 \
    alsa-utils \
    ffmpeg \
    libportaudio2 \
    portaudio19-dev \
    wget \
    gnupg2 \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# Add NVIDIA CUDA GPG key and repository for Ubuntu 22.04 (Humble base)
RUN wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb && \
    dpkg -i cuda-keyring_1.1-1_all.deb && \
    apt-get update && \
    apt-get install -y cuda-toolkit-12-1 && \
    rm -rf /var/lib/apt/lists/*

# Set CUDA environment variables
ENV CUDA_HOME=/usr/local/cuda-12.1
ENV PATH=${CUDA_HOME}/bin:${PATH}
ENV LD_LIBRARY_PATH=${CUDA_HOME}/lib64

# Set working directory
WORKDIR /app

# Copy requirements file first for layer caching
COPY requirements.txt .

# Install Python dependencies
# Note: torch must be installed FIRST because flash-attn's setup.py imports it.
RUN pip3 install --no-cache-dir torch

# Install the rest of the requirements
RUN pip3 install --no-cache-dir -r requirements.txt

# Add additional system dependencies here to avoid rebuilding heavy layers (cache optimization).
# Added libasound2-plugins for PulseAudio/PipeWire support.
RUN apt-get update && apt-get install -y sox libasound2-plugins libsox-fmt-all && rm -rf /var/lib/apt/lists/*

# Build arguments for user configuration
ARG USER_UID=1000
ARG USER_GID=1000
ARG USERNAME=rosuser

# Create user with configurable UID/GID to match host user and avoid getpwuid() errors.
# Also add user to audio and video groups for hardware access.
RUN groupadd -g ${USER_GID} ${USERNAME} 2>/dev/null || true && \
    useradd -m -u ${USER_UID} -g ${USER_GID} -s /bin/bash ${USERNAME} 2>/dev/null || true && \
    usermod -aG audio,video ${USERNAME}

# Create directory for ROS logs in /tmp and ensure user can write to it
RUN mkdir -p /tmp/ros && chown -R ${USERNAME}:${USERNAME} /tmp/ros

# Create the ROS 2 workspace structure and set ownership
WORKDIR /app/ros2_ws/src/bob_q3tts
COPY . .
RUN chown -R ${USERNAME}:${USERNAME} /app

# Switch to the user for building and running
USER ${USERNAME}
WORKDIR /app/ros2_ws

# Source ROS 2 and build the package as the user
RUN . /opt/ros/${ROS_DISTRO}/setup.sh && \
    colcon build --packages-select bob_q3tts

# Set ROS logging directories and HOME
ENV HOME=/home/${USERNAME}
ENV ROS_HOME=/tmp/ros
ENV ROS_LOG_DIR=/tmp/ros/log

# Add ALSA configuration to use PulseAudio as default
USER root
RUN echo "pcm.!default {\n    type pulse\n    fallback \"sysdefault\"\n}\n\nctl.!default {\n    type pulse\n    fallback \"sysdefault\"\n}" > /etc/asound.conf
USER ${USERNAME}

# Prepare entrypoint
COPY <<'EOF' /tmp/entrypoint.sh
#!/bin/bash
set -e
source /opt/ros/${ROS_DISTRO}/setup.bash
source /app/ros2_ws/install/setup.bash
exec "$@"
EOF

USER root
RUN mv /tmp/entrypoint.sh /entrypoint.sh && chmod +x /entrypoint.sh
USER ${USERNAME}

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "run", "bob_q3tts", "tts"]

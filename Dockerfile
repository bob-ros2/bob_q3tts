# --- STAGE 1: Builder ---
ARG ROS_DISTRO=humble
FROM ros:${ROS_DISTRO}-ros-base AS builder

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    python3-pip \
    wget \
    gnupg2 \
    software-properties-common \
    build-essential \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# Add NVIDIA CUDA GPG key and repository for building (need nvcc for flash-attn)
RUN wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb && \
    dpkg -i cuda-keyring_1.1-1_all.deb && \
    apt-get update && \
    apt-get install -y cuda-nvcc-12-1 cuda-libraries-dev-12-1 && \
    rm -rf /var/lib/apt/lists/*

# Set CUDA environment variables for building
ENV CUDA_HOME=/usr/local/cuda-12.1
ENV PATH=${CUDA_HOME}/bin:${PATH}

# Install Python dependencies into a local path
COPY requirements.txt .
RUN pip3 install --no-cache-dir --user torch -r requirements.txt

# Build ROS 2 workspace
COPY . ros2_ws/src/bob_q3tts/
WORKDIR /app/ros2_ws
RUN . /opt/ros/${ROS_DISTRO}/setup.sh && \
    colcon build --packages-select bob_q3tts

# --- STAGE 2: Runtime ---
FROM ros:${ROS_DISTRO}-ros-base

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ARG USERNAME=rosuser
ARG USER_UID=1000
ARG USER_GID=1000

# Install only runtime system dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    libasound2 \
    alsa-utils \
    ffmpeg \
    libportaudio2 \
    sox \
    libasound2-plugins \
    libsox-fmt-all \
    && rm -rf /var/lib/apt/lists/*

# Install ONLY minimal CUDA runtime (torch brings its own libs, so we only need the bare essentials)
RUN apt-get update && apt-get install -y wget gnupg2 && \
    wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb && \
    dpkg -i cuda-keyring_1.1-1_all.deb && \
    apt-get update && \
    apt-get install -y cuda-cudart-12-1 && \
    apt-get purge -y wget gnupg2 && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Create user with matching host UID/GID
RUN groupadd -g ${USER_GID} ${USERNAME} 2>/dev/null || true && \
    useradd -m -u ${USER_UID} -g ${USER_GID} -s /bin/bash ${USERNAME} 2>/dev/null || true && \
    usermod -aG audio,video ${USERNAME}

# Copy built Python packages and ROS installation from builder with correct ownership
# This avoids the extra layer size from a separate 'chown -R' command
COPY --from=builder --chown=${USERNAME}:${USERNAME} /root/.local /home/${USERNAME}/.local
COPY --from=builder --chown=${USERNAME}:${USERNAME} /app/ros2_ws/install /app/ros2_ws/install

# ALSA configuration for PulseAudio
RUN echo "pcm.!default {\n    type pulse\n    fallback \"sysdefault\"\n}\n\nctl.!default {\n    type pulse\n    fallback \"sysdefault\"\n}" > /etc/asound.conf

# Environment variables for execution
ENV HOME=/home/${USERNAME}
ENV PATH=${HOME}/.local/bin:${PATH}
ENV PYTHONPATH=${HOME}/.local/lib/python3.10/site-packages
ENV ROS_HOME=/tmp/ros
ENV ROS_LOG_DIR=/tmp/ros/log

# Prepare directory for logs
RUN mkdir -p /tmp/ros && chown -R ${USERNAME}:${USERNAME} /tmp/ros

# Prepare entrypoint
COPY --chmod=755 <<'EOF' /entrypoint.sh
#!/bin/bash
set -e
source /opt/ros/${ROS_DISTRO}/setup.bash
if [ -f "/app/ros2_ws/install/setup.bash" ]; then
    source /app/ros2_ws/install/setup.bash
fi
exec "$@"
EOF

USER ${USERNAME}
WORKDIR /app/ros2_ws

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "run", "bob_q3tts", "tts"]

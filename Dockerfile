# --- ARG Configuration ---
ARG ROS_DISTRO=humble
ARG CUDA_VERSION=12.1.1
ARG TORCH_CUDA_VERSION=cu121
ARG UBUNTU_VERSION=22.04

# --- STAGE 1: Builder ---
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION} AS builder

ARG ROS_DISTRO
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install ROS 2 base and system build tools
RUN apt-get update && apt-get install -y \
    software-properties-common curl gnupg2 lsb-release \
    && curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/ros2.list > /dev/null \
    && apt-get update && apt-get install -y \
    python3-pip python3-venv python3-colcon-common-extensions \
    ninja-build build-essential \
    ros-${ROS_DISTRO}-ros-base \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

# Fix for flash-attn build (compile with multicore)
ENV MAX_JOBS=4
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=${CUDA_HOME}/bin:${PATH}

# Install PyTorch and Dependencies with MATCHING CUDA version
COPY requirements.txt .
RUN pip3 install --no-cache-dir --user \
    torch --index-url https://download.pytorch.org/whl/cu121 && \
    pip3 install --no-cache-dir --user -r requirements.txt

# Build ROS 2 workspace
COPY . ros2_ws/src/bob_q3tts/
WORKDIR /app/ros2_ws
RUN . /opt/ros/humble/setup.sh && \
    colcon build --packages-select bob_q3tts --cmake-args -DCMAKE_BUILD_TYPE=Release

# --- STAGE 2: Runtime ---
FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION}

ARG ROS_DISTRO=humble
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ARG USERNAME=rosuser

# Install ROS 2 runtime and audio dependencies
RUN apt-get update && apt-get install -y \
    software-properties-common curl gnupg2 lsb-release \
    && curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/ros2.list > /dev/null \
    && apt-get update && apt-get install -y \
    ros-${ROS_DISTRO}-ros-base \
    python3-pip \
    libasound2 alsa-utils ffmpeg libportaudio2 sox libasound2-plugins libsox-fmt-all \
    && rm -rf /var/lib/apt/lists/*

# User Setup (matching host UID 1000)
RUN groupadd -g 1000 ${USERNAME} && \
    useradd -m -u 1000 -g 1000 -s /bin/bash ${USERNAME} && \
    usermod -aG audio,video ${USERNAME}

# Copy results from builder (slims down image from 6GB to ~3.5GB)
COPY --from=builder --chown=${USERNAME}:${USERNAME} /root/.local /home/${USERNAME}/.local
COPY --from=builder --chown=${USERNAME}:${USERNAME} /app/ros2_ws/install /app/ros2_ws/install

# Audio Config
RUN echo "pcm.!default { type pulse fallback \"sysdefault\" } \n ctl.!default { type pulse fallback \"sysdefault\" }" > /etc/asound.conf

ENV HOME=/home/${USERNAME}
ENV PATH=${HOME}/.local/bin:${PATH}
ENV PYTHONPATH=${HOME}/.local/lib/python3.10/site-packages
ENV ROS_HOME=/tmp/ros

WORKDIR /app/ros2_ws
USER ${USERNAME}

ENTRYPOINT ["bash", "-c", "source /opt/ros/humble/setup.bash && source install/setup.bash && exec \"$@\""]
CMD ["ros2", "run", "bob_q3tts", "tts"]

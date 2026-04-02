# --- ARG Configuration ---
ARG ROS_DISTRO=humble
ARG CUDA_VERSION=12.4.1
ARG TORCH_CUDA_VERSION=cu124
ARG UBUNTU_VERSION=22.04

# --- STAGE 1: Builder ---
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION} AS builder

ARG ROS_DISTRO
ARG TORCH_CUDA_VERSION
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

# Install Dependencies GLOBALLY (in /usr/local)
COPY requirements.txt .
# Lock PyTorch to 2.10.0 across ALL builds (prevents background pip from pulling newer CU130 versions)
RUN echo "torch==2.10.0\ntorchaudio==2.10.0" > /tmp/constraint.txt
ENV PIP_CONSTRAINT=/tmp/constraint.txt

RUN pip3 install --no-cache-dir torch==2.10.0 torchvision torchaudio && \
    pip3 install --no-cache-dir -r requirements.txt

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
ARG USERNAME=ros
ARG USER_UID=1000
ARG USER_GID=1000

# Install ROS 2 runtime and EVERYTHING needed for GUI/Audio
RUN apt-get update && apt-get install -y \
    software-properties-common curl gnupg2 lsb-release \
    && curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/ros2.list > /dev/null \
    && apt-get update && apt-get install -y \
    ros-${ROS_DISTRO}-ros-base \
    python3-pip \
    libasound2 alsa-utils ffmpeg libportaudio2 sox libasound2-plugins libsox-fmt-all \
    libqt5gui5 libqt5widgets5 libqt5core5a libqt5dbus5 libqt5network5 \
    libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xkb1 libxkbcommon-x11-0 \
    libpulse0 libpulse-mainloop-glib0 libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

# User Setup
RUN groupadd -g ${USER_GID} ${USERNAME} && \
    useradd -m -u ${USER_UID} -g ${USER_GID} -s /bin/bash ${USERNAME} && \
    usermod -aG audio,video ${USERNAME}

# Copy EVERYTHING from builder /usr/local to /usr/local
# This includes all Python packages (Torch, Transformers, ONNX) and Flash-Attn
COPY --from=builder /usr/local /usr/local
COPY --from=builder --chown=${USERNAME}:${USERNAME} /app/ros2_ws/install /app/ros2_ws/install

# Audio Config
RUN printf 'pcm.!default { type pulse fallback "sysdefault" }\nctl.!default { type pulse fallback "sysdefault" }\n' > /etc/asound.conf

ENV HOME=/home/${USERNAME}
ENV PATH=${HOME}/.local/bin:${PATH}
# No more PYTHONPATH mess, we use the global dist-packages
# Set LD_LIBRARY_PATH to find shared libraries in global site-packages
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.10/dist-packages/torch/lib:/usr/local/lib/python3.10/dist-packages/nvidia/cuda_runtime/lib:/usr/local/lib/python3.10/dist-packages/nvidia/cuda_cupti/lib:${LD_LIBRARY_PATH}
ENV ROS_HOME=/tmp/ros

WORKDIR /app/ros2_ws
USER ${USERNAME}

ENTRYPOINT ["/bin/bash", "-c", "source /opt/ros/humble/setup.bash && source install/setup.bash && exec \"$@\"", "--"]
CMD ["ros2", "run", "bob_q3tts", "tts"]

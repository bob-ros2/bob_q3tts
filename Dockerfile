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
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file first for layer caching
COPY requirements.txt .

# Install Python dependencies
# Note: torch and flash-attn might take some time and require GPU headers for best performance.
# We use --no-cache-dir to keep the image small.
RUN pip3 install --no-cache-dir -r requirements.txt

# Create the ROS 2 workspace structure
RUN mkdir -p /app/ros2_ws/src/bob_q3tts

# Copy the package source code
COPY . /app/ros2_ws/src/bob_q3tts

# Source ROS 2 and build the package
WORKDIR /app/ros2_ws
RUN . /opt/ros/${ROS_DISTRO}/setup.sh && \
    colcon build --packages-select bob_q3tts

# Prepare entrypoint
RUN echo "#!/bin/bash\nset -e\n. /opt/ros/${ROS_DISTRO}/setup.sh\n. /app/ros2_ws/install/setup.sh\nexec \"\$@\"" > /entrypoint.sh && \
    chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "run", "bob_q3tts", "tts"]

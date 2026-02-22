# Use a Kali Linux base image
FROM kalilinux/kali-rolling

# Set environment variables
ENV PYTHONUNBUFFERED 1

# Install Python and pip
RUN apt update && apt install -y \
    python3 \
    python3-pip \
    git \
    sudo \
    # Install common pentesting tools that are used in HiesenMCP server
    nmap \
    gobuster \
    dirb \
    nikto \
    sqlmap \
    metasploit-framework \
    hydra \
    john \
    wpscan \
    enum4linux \
    ffuf \
    gdb \
    radare2 \
    binutils # Provides objdump and readelf

# Install Python dependencies and Python-based tools
RUN pip3 install fastmcp flask requests \
    frida-tools \
    drozer \
    objection \
    semgrep \
    bandit

# Note: cycript and needle are often specific to mobile environments (e.g., jailbroken iOS)
# and are not easily installed on a standard Kali Linux Docker image via apt or pip.
# If needed, these would require a more specialized Docker image or manual setup.

# Set the working directory in the container
WORKDIR /app

# Copy the application files into the container
COPY src /app/src
COPY config /app/config
COPY data /app/data
COPY logs /app/logs

# Expose the port the Flask app will run on
EXPOSE 1337

# Command to run the Flask application
CMD ["python3", "src/server/hiesenMCPServer.py"]

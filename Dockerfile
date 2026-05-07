# Use a Kali Linux base image
FROM kalilinux/kali-rolling

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/hiesen-mcp-venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

# Install Python and pip
RUN apt update && apt install -y \
    python3 \
    python3-pip \
    git \
    sudo \
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
    binutils     # Provides objdump and readelf

RUN apt update && apt install -y --no-install-recommends \
    build-essential python3-dev python3-venv libffi-dev libssl-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies and Python-based tools
RUN python3 -m venv "$VIRTUAL_ENV" \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir \
        fastmcp==3.2.4 \
        flask==3.1.2 \
        requests==2.33.1 \
        frida-tools==12.5.1 \
        drozer==3.1.0 \
        objection==1.12.4 \
        semgrep==1.85.0 \
        bandit==1.9.4

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

# HiesenMCP

HiesenMCP is a client-server application designed to streamline penetration testing by providing a centralized interface to a wide range of security tools. The server runs on a Kali Linux environment and exposes a REST API, which the client uses to execute tools and manage tasks.

## Features

- **Remote Tool Execution:** Run a variety of popular penetration testing tools on a remote Kali Linux machine.
- **Supported Tools:**
    - Network Scanners: `nmap`
    - Web Scanners: `gobuster`, `dirb`, `nikto`, `wpscan`, `ffuf`
    - Vulnerability Scanners: `sqlmap`
    - Exploitation: `metasploit`
    - Password Crackers: `hydra`, `john`
    - Enumeration: `enum4linux`
    - Mobile: `frida`, `drozer`, `objection`, `cycript`, `needle`
    - Static Analysis: `semgrep`, `bandit`
    - Binary Analysis: `gdb`, `radare2`, `strings`, `objdump`, `readelf`
- **File Upload:** Upload files to the server for use with various tools.
- **Command Execution:** Execute arbitrary shell commands on the server.
- **Knowledge Base:** A simple knowledge base to store and retrieve information about tools and test cases.
- **Docker Support:** The server can be easily deployed using Docker.

## Project Structure

```
HiesenMCP/
├── .gitignore
├── Dockerfile
├── config/
│   └── system_prompt.txt
├── data/
│   ├── knowledge_base/
│   └── wordlists/
├── docs/
├── logs/
├── reference/
└── src/
    ├── client/
    │   └── hiesenMCPClient.py
    └── server/
        └── hiesenMCPServer.py
```

- **`src/server/hiesenMCPServer.py`**: The Flask-based server that runs on Kali Linux and exposes the API.
- **`src/client/hiesenMCPClient.py`**: The client application for interacting with the server.
- **`Dockerfile`**: For building the Docker image for the server.
- **`data/knowledge_base`**: Contains JSON files for the knowledge base.
- **`data/wordlists`**: Directory for storing wordlists.

## Setup

### Server Setup (Docker)

1.  **Build the Docker image:**
    ```bash
    docker build -t hiesen-mcp .
    ```

2.  **Run the Docker container:**
    ```bash
    docker run -d -p 1337:1337 --name hiesen-mcp-container hiesen-mcp
    ```
    The server will be running on `http://localhost:1337`.

    To download the larger optional wordlist repositories on startup:
    ```bash
    docker run -d -p 1337:1337 -e HIESENMCP_DOWNLOAD_WORDLISTS=1 --name hiesen-mcp-container hiesen-mcp
    ```

### Server Setup (Manual)

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd HiesenMCP
    ```

2.  **Install dependencies:**
    ```bash
    pip install flask fastmcp
    ```
    *(For a full pentesting toolchain, install the required Kali tools on the host. The Docker image handles this automatically.)*

3.  **Run the server:**
    ```bash
    python3 src/server/hiesenMCPServer.py
    ```

### Client Setup

1.  **Install dependencies:**
    ```bash
    pip install requests fastmcp
    ```

2.  **Run the client:**
    ```bash
    python3 src/client/hiesenMCPClient.py --server http://<server-ip>:1337
    ```
    This starts the MCP client over stdio so an MCP-capable host can call its tools.

## Usage

The server exposes REST endpoints under `/api/*`. You can call them directly, or use `src/client/hiesenMCPClient.py` through an MCP-capable host.

### Example: Running an Nmap Scan

```bash
curl -sS -X POST http://localhost:1337/api/tools/nmap \
  -H "Content-Type: application/json" \
  -d '{"target":"192.168.1.1","scan_type":"-sV","additional_args":"-T4 -Pn"}'
```

### Example: Uploading a File

```bash
curl -sS -X POST http://localhost:1337/api/upload_file \
  -F "file=@/path/to/your/file"
```

### Example: Executing a Command

```bash
curl -sS -X POST http://localhost:1337/api/command \
  -H "Content-Type: application/json" \
  -d '{"command":"ls -la"}'
```

## Integrating with AI Clients

To integrate HiesenMCP with your AI client, configure the client's MCP settings with the connection details for the HiesenMCP server.

### LM Studio on Windows

LM Studio on Windows can launch the MCP client inside the running Docker container, so you do not need to install Python dependencies on Windows:

1.  Confirm the API container is running:
    ```bash
    docker ps --filter name=hiesen-mcp-container
    ```

2.  In LM Studio, open **Program > Install > Edit mcp.json**.

3.  Add the contents of `docs/lmstudio-windows-mcp.json`.

If Windows PowerShell cannot see the container but WSL can, use `docs/lmstudio-windows-wsl-mcp.json` instead.

If LM Studio cannot find `docker`, replace `"command": "docker"` with the full path to `docker.exe`, for example:

```json
"command": "C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe"
```

### Other MCP Clients

1.  **Locate `connection.json`:** This file is typically found in the `docs/` directory of the HiesenMCP project.
    ```json
    {
        "mcpServers": {
            "HiesenMCP": {
                "command": "python3",
                "args": [
                    "src/client/hiesenMCPClient.py",
                    "--server",
                    "http://127.0.0.1:1337"
                ]
            }
        }
    }
    ```

2.  **Copy Configuration:** Copy the content of the `HiesenMCP` entry from `connection.json` into your AI client's MCP configuration. The exact location and format will depend on your AI client.

    **Important:**
    - Run this command from the project root, or replace `src/client/hiesenMCPClient.py` with an absolute path.
    - Adjust the `--server` URL (`http://127.0.0.1:1337`) if your HiesenMCP server is running on a different IP address or port.

This configuration allows your AI client to discover and utilize the tools exposed by the HiesenMCP server.

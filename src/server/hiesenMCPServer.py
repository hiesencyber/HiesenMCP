#!/usr/bin/env python3

import logging
import os
import subprocess
import sys
import traceback
import threading
from typing import Dict, Any
from flask import Flask, request, jsonify
from datetime import datetime
import json
from pathlib import Path

# ... (rest of the imports) ...

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
KNOWLEDGE_BASE_DIR = DATA_DIR / "knowledge_base"
WORDLISTS_DIR = DATA_DIR / "wordlists"
LOGS_DIR = BASE_DIR / "logs"
LOG_FILE_PATH = LOGS_DIR / "actionErrorlog.md"

def _log_error_to_file(error_message: str, traceback_info: str, context: str = "General Error"):
    """Logs error details to actionErrorlog.md."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file_path = LOG_FILE_PATH
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file_path, "a") as f:
        f.write(f"## Error Log Entry - {timestamp}\n")
        f.write(f"**Context:** {context}\n")
        f.write(f"**Error Message:** {error_message}\n")
        f.write(f"**Traceback:**\n```\n{traceback_info}\n```\n")
        f.write("---\n\n")

# Assuming FastMCP is available in the environment or can be installed.
# For a basic model, we'll assume it's either installed or we'll provide a placeholder if not.
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("FastMCP not found. Please install it (e.g., pip install fastmcp) or ensure it's in your PYTHONPATH.", file=sys.stderr)
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration
COMMAND_TIMEOUT = 180  # 3 minutes default timeout for command execution
API_PORT = int(os.environ.get("API_PORT", 1337)) # Default to 1337

app = Flask(__name__)

@app.before_request
def log_request_info():
    logger.info(f"Incoming Request: {request.method} {request.url}")
    if request.is_json:
        logger.info(f"Request JSON Data: {request.json}")

class CommandExecutor:
    """Class to handle command execution with better timeout management"""
    
    def __init__(self, command: str, timeout: int = COMMAND_TIMEOUT):
        self.command = command
        self.timeout = timeout
        self.process = None
        self.stdout_data = ""
        self.stderr_data = ""
        self.stdout_thread = None
        self.stderr_thread = None
        self.return_code = None
        self.timed_out = False
    
    def _read_stdout(self):
        """Thread function to continuously read stdout"""
        for line in iter(self.process.stdout.readline, ''):
            self.stdout_data += line
    
    def _read_stderr(self):
        """Thread function to continuously read stderr"""
        for line in iter(self.process.stderr.readline, ''):
            self.stderr_data += line
    
    def execute(self) -> Dict[str, Any]:
        """Execute the command and handle timeout gracefully"""
        logger.info(f"Executing command: {self.command}")
        
        try:
            self.process = subprocess.Popen(
                self.command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Line buffered
            )
            
            # Start threads to read output continuously
            self.stdout_thread = threading.Thread(target=self._read_stdout)
            self.stderr_thread = threading.Thread(target=self._read_stderr)
            self.stdout_thread.daemon = True
            self.stderr_thread.daemon = True
            self.stdout_thread.start()
            self.stderr_thread.start()
            
            # Wait for the process to complete or timeout
            try:
                self.return_code = self.process.wait(timeout=self.timeout)
                # Process completed, join the threads
                self.stdout_thread.join()
                self.stderr_thread.join()
            except subprocess.TimeoutExpired:
                # Process timed out but we might have partial results
                self.timed_out = True
                logger.warning(f"Command timed out after {self.timeout} seconds. Terminating process.")
                
                # Try to terminate gracefully first
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)  # Give it 5 seconds to terminate
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate
                    logger.warning("Process not responding to termination. Killing.")
                    self.process.kill()
                
                # Update final output
                self.return_code = -1
            
            # Always consider it a success if we have output, even with timeout
            success = True if self.timed_out and (self.stdout_data or self.stderr_data) else (self.return_code == 0)
            
            return {
                "stdout": self.stdout_data,
                "stderr": self.stderr_data,
                "return_code": self.return_code,
                "success": success,
                "timed_out": self.timed_out,
                "partial_results": self.timed_out and (self.stdout_data or self.stderr_data)
            }
        
        except Exception as e:
            error_message = f"Error executing command: {str(e)}"
            traceback_info = traceback.format_exc()
            logger.error(error_message)
            logger.error(traceback_info)
            _log_error_to_file(error_message, traceback_info, context=f"Command Execution: {self.command}")
            return {
                "stdout": self.stdout_data,
                "stderr": f"Error executing command: {str(e)}",
                "return_code": -1,
                "success": False,
                "timed_out": False,
                "partial_results": bool(self.stdout_data or self.stderr_data)
            }

def _check_and_install_tool(tool_name: str) -> bool:
    """
    Checks if a tool is installed and installs it if not found using apt.
    Returns True if the tool is available, False otherwise.
    """
    logger.info(f"Checking for tool: {tool_name}")
    try:
        # Check if the tool exists
        subprocess.run(["which", tool_name], check=True, capture_output=True)
        logger.info(f"Tool '{tool_name}' already installed.")
        return True
    except subprocess.CalledProcessError:
        logger.warning(f"Tool '{tool_name}' not found. Attempting to install...")
        try:
            # Update apt and install the tool
            update_result = subprocess.run(["sudo", "apt", "update"], check=True, capture_output=True, text=True)
            logger.info(f"apt update stdout: {update_result.stdout}")
            if update_result.stderr:
                logger.warning(f"apt update stderr: {update_result.stderr}")

            install_result = subprocess.run(["sudo", "apt", "install", "-y", tool_name], check=True, capture_output=True, text=True)
            logger.info(f"apt install stdout: {install_result.stdout}")
            if install_result.stderr:
                logger.warning(f"apt install stderr: {install_result.stderr}")
            logger.info(f"Tool '{tool_name}' installed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            error_message = f"Failed to install tool '{tool_name}': {e}"
            traceback_info = traceback.format_exc()
            logger.error(error_message)
            logger.error(f"Install stdout: {e.stdout}")
            logger.error(f"Install stderr: {e.stderr}")
            _log_error_to_file(error_message, traceback_info, context=f"Tool Installation: {tool_name}")
            return False
        except Exception as e:
            error_message = f"An unexpected error occurred during tool installation: {e}"
            traceback_info = traceback.format_exc()
            logger.error(error_message)
            _log_error_to_file(error_message, traceback_info, context=f"Tool Installation: {tool_name}")
            return False

# Helper function to execute commands with tool check and installation
def execute_command_with_check(command: str) -> Dict[str, Any]:
    tool_name = command.split(" ")[0] # Basic extraction of tool name
    if not _check_and_install_tool(tool_name):
        return {
            "stdout": "",
            "stderr": f"Tool '{tool_name}' is not installed and could not be installed.",
            "return_code": -1,
            "success": False,
            "timed_out": False,
            "partial_results": False
        }
    executor = CommandExecutor(command)
    return executor.execute()

@app.route("/api/command", methods=["POST"])
def generic_command():
    """Execute any command provided in the request."""
    try:
        params = request.json
        command = params.get("command", "")
        
        if not command:
            logger.warning("Command endpoint called without command parameter")
            return jsonify({
                "error": "Command parameter is required"
            }), 400
        
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in command endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Generic Command Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/nmap", methods=["POST"])
def nmap():
    """Execute nmap scan with the provided parameters."""
    try:
        params = request.json
        target = params.get("target", "")
        scan_type = params.get("scan_type", "-sCV")
        ports = params.get("ports", "")
        additional_args = params.get("additional_args", "-T4 -Pn")
        
        if not target:
            logger.warning("Nmap called without target parameter")
            return jsonify({
                "error": "Target parameter is required"
            }), 400        
        
        command = f"nmap {scan_type}"
        
        if ports:
            command += f" -p {ports}"
        
        if additional_args:
            command += f" {additional_args}"
        
        command += f" {target}"
        
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in nmap endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Nmap Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/gobuster", methods=["POST"])
def gobuster():
    """Execute gobuster with the provided parameters."""
    try:
        params = request.json
        url = params.get("url", "")
        mode = params.get("mode", "dir")
        wordlist = params.get("wordlist", "/usr/share/wordlists/dirb/common.txt")
        additional_args = params.get("additional_args", "")
        
        if not url:
            logger.warning("Gobuster called without URL parameter")
            return jsonify({
                "error": "URL parameter is required"
            }), 400
        
        if mode not in ["dir", "dns", "fuzz", "vhost"]:
            logger.warning(f"Invalid gobuster mode: {mode}")
            return jsonify({
                "error": f"Invalid mode: {mode}. Must be one of: dir, dns, fuzz, vhost"
            }), 400
        
        command = f"gobuster {mode} -u {url} -w {wordlist}"
        
        if additional_args:
            command += f" {additional_args}"
        
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in gobuster endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Gobuster Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/dirb", methods=["POST"])
def dirb():
    """Execute dirb with the provided parameters."""
    try:
        params = request.json
        url = params.get("url", "")
        wordlist = params.get("wordlist", "/usr/share/wordlists/dirb/common.txt")
        additional_args = params.get("additional_args", "")
        
        if not url:
            logger.warning("Dirb called without URL parameter")
            return jsonify({
                "error": "URL parameter is required"
            }), 400
        
        command = f"dirb {url} {wordlist}"
        
        if additional_args:
            command += f" {additional_args}"
        
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in dirb endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Dirb Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/nikto", methods=["POST"])
def nikto():
    """Execute nikto with the provided parameters."""
    try:
        params = request.json
        target = params.get("target", "")
        additional_args = params.get("additional_args", "")
        
        if not target:
            logger.warning("Nikto called without target parameter")
            return jsonify({
                "error": "Target parameter is required"
            }), 400
        
        command = f"nikto -h {target}"
        
        if additional_args:
            command += f" {additional_args}"
        
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in nikto endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Nikto Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/sqlmap", methods=["POST"])
def sqlmap():
    """Execute sqlmap with the provided parameters."""
    try:
        params = request.json
        url = params.get("url", "")
        data = params.get("data", "")
        additional_args = params.get("additional_args", "")
        
        if not url:
            logger.warning("SQLMap called without URL parameter")
            return jsonify({
                "error": "URL parameter is required"
            }), 400
        
        command = f"sqlmap -u {url} --batch"
        
        if data:
            command += f" --data=\"{data}\""
        
        if additional_args:
            command += f" {additional_args}"
        
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in sqlmap endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="SQLMap Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/metasploit", methods=["POST"])
def metasploit():
    """Execute metasploit module with the provided parameters."""
    try:
        params = request.json
        module = params.get("module", "")
        options = params.get("options", {})
        
        if not module:
            logger.warning("Metasploit called without module parameter")
            return jsonify({
                "error": "Module parameter is required"
            }), 400
        
        resource_content = f"use {module}\n"
        for key, value in options.items():
            resource_content += f"set {key} {value}\n"
        resource_content += "exploit\n"
        
        resource_file = "/tmp/mcp_msf_resource.rc"
        with open(resource_file, "w") as f:
            f.write(resource_content)
        
        command = f"msfconsole -q -r {resource_file}"
        result = execute_command_with_check(command)
        
        try:
            os.remove(resource_file)
        except Exception as e:
            logger.warning(f"Error removing temporary resource file: {str(e)}")
        
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in metasploit endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Metasploit Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/hydra", methods=["POST"])
def hydra():
    """Execute hydra with the provided parameters."""
    try:
        params = request.json
        target = params.get("target", "")
        service = params.get("service", "")
        username = params.get("username", "")
        username_file = params.get("username_file", "")
        password = params.get("password", "")
        password_file = params.get("password_file", "")
        additional_args = params.get("additional_args", "")
        
        if not target or not service:
            logger.warning("Hydra called without target or service parameter")
            return jsonify({
                "error": "Target and service parameters are required"
            }), 400
        
        if not (username or username_file) or not (password or password_file):
            logger.warning("Hydra called without username/password parameters")
            return jsonify({
                "error": "Username/username_file and password/password_file are required"
            }), 400
        
        command = f"hydra -t 4"
        
        if username:
            command += f" -l {username}"
        elif username_file:
            command += f" -L {username_file}"
        
        if password:
            command += f" -p {password}"
        elif password_file:
            command += f" -P {password_file}"
        
        if additional_args:
            command += f" {additional_args}"
        
        command += f" {target} {service}"
        
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in hydra endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Hydra Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/john", methods=["POST"])
def john():
    """Execute john with the provided parameters."""
    try:
        params = request.json
        hash_file = params.get("hash_file", "")
        wordlist = params.get("wordlist", "/usr/share/wordlists/rockyou.txt")
        format_type = params.get("format", "")
        additional_args = params.get("additional_args", "")
        
        if not hash_file:
            logger.warning("John called without hash_file parameter")
            return jsonify({
                "error": "Hash file parameter is required"
            }), 400
        
        command = f"john"
        
        if format_type:
            command += f" --format={format_type}"
        
        if wordlist:
            command += f" --wordlist={wordlist}"
        
        if additional_args:
            command += f" {additional_args}"
        
        command += f" {hash_file}"
        
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in john endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="John Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/wpscan", methods=["POST"])
def wpscan():
    """Execute wpscan with the provided parameters."""
    try:
        params = request.json
        url = params.get("url", "")
        additional_args = params.get("additional_args", "")
        
        if not url:
            logger.warning("WPScan called without URL parameter")
            return jsonify({
                "error": "URL parameter is required"
            }), 400
        
        command = f"wpscan --url {url}"
        
        if additional_args:
            command += f" {additional_args}"
        
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in wpscan endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="WPScan Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/enum4linux", methods=["POST"])
def enum4linux():
    """Execute enum4linux with the provided parameters."""
    try:
        params = request.json
        target = params.get("target", "")
        additional_args = params.get("additional_args", "-a")
        
        if not target:
            logger.warning("Enum4linux called without target parameter")
            return jsonify({
                "error": "Target parameter is required"
            }), 400
        
        command = f"enum4linux {additional_args} {target}"
        
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in enum4linux endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Enum4linux Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/ffuf", methods=["POST"])
def ffuf_scan():
    """Execute ffuf with the provided parameters."""
    try:
        params = request.json
        url = params.get("url", "")
        wordlist = params.get("wordlist", "")
        headers = params.get("headers", {})
        method = params.get("method", "GET")
        post_data = params.get("post_data", "")
        match_codes = params.get("match_codes", "")
        filter_codes = params.get("filter_codes", "")
        follow_redirects = params.get("follow_redirects", False)
        recursion = params.get("recursion", False)
        threads = params.get("threads", 40)
        mode = params.get("mode", "") # Multi-wordlist operation mode
        additional_args = params.get("additional_args", "")

        if not url or not wordlist:
            logger.warning("FFUF called without URL or wordlist parameter")
            return jsonify({
                "error": "URL and wordlist parameters are required"
            }), 400
        
        command = f"ffuf -w {wordlist} -u {url}"

        if headers:
            for key, value in headers.items():
                command += f" -H \"{key}: {value}\""
        if method != "GET":
            command += f" -X {method}"
        if post_data:
            command += f" -d '{post_data}'"
        if match_codes:
            command += f" -mc {match_codes}"
        if filter_codes:
            command += f" -fc {filter_codes}"
        if follow_redirects:
            command += " -r"
        if recursion:
            command += " -recursion"
        if threads != 40:
            command += f" -t {threads}"
        if mode:
            command += f" -mode {mode}"
        
        if additional_args:
            command += f" {additional_args}"
        
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in ffuf_scan endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="FFUF Scan Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500


@app.route("/api/tools/frida", methods=["POST"])
def frida_run():
    """Execute Frida with the provided parameters."""
    try:
        params = request.json
        script = params.get("script", "")
        target = params.get("target", "")
        additional_args = params.get("additional_args", "")

        if not script or not target:
            logger.warning("Frida called without script or target parameter")
            return jsonify({
                "error": "Script and target parameters are required"
            }), 400
        
        command = f"frida -l {script} -f {target} --no-pause {additional_args}"
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in frida_run endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Frida Run Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/drozer", methods=["POST"])
def drozer_run():
    """Execute Drozer with the provided parameters."""
    try:
        params = request.json
        command_args = params.get("command_args", "")

        if not command_args:
            logger.warning("Drozer called without command_args parameter")
            return jsonify({
                "error": "command_args parameter is required"
            }), 400
        
        command = f"drozer {command_args}"
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in drozer_run endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Drozer Run Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/objection", methods=["POST"])
def objection_run():
    """Execute Objection with the provided parameters."""
    try:
        params = request.json
        gadget = params.get("gadget", "")
        command_args = params.get("command_args", "")

        if not gadget or not command_args:
            logger.warning("Objection called without gadget or command_args parameter")
            return jsonify({
                "error": "Gadget and command_args parameters are required"
            }), 400
        
        command = f"objection --gadget {gadget} explore {command_args}"
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in objection_run endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Objection Run Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/cycript", methods=["POST"])
def cycript_run():
    """Execute Cycript with the provided parameters."""
    try:
        params = request.json
        process_id = params.get("process_id", "")
        script = params.get("script", "")
        additional_args = params.get("additional_args", "")

        if not process_id and not script:
            logger.warning("Cycript called without process_id or script parameter")
            return jsonify({
                "error": "process_id or script parameter is required"
            }), 400
        
        command = f"cycript"
        if process_id:
            command += f" -p {process_id}"
        if script:
            command += f" {script}"
        if additional_args:
            command += f" {additional_args}"

        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in cycript_run endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Cycript Run Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500


@app.route("/api/tools/needle", methods=["POST"])
def needle_run():
    """Execute Needle with the provided parameters."""
    try:
        params = request.json
        command_args = params.get("command_args", "")

        if not command_args:
            logger.warning("Needle called without command_args parameter")
            return jsonify({
                "error": "command_args parameter is required"
            }), 400
        
        command = f"needle {command_args}"
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in needle_run endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Needle Run Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/semgrep", methods=["POST"])
def semgrep_scan():
    """Execute Semgrep for static code analysis."""
    try:
        params = request.json
        target_path = params.get("target_path", ".")
        config = params.get("config", "auto") # e.g., --config=auto, --config=p/python
        additional_args = params.get("additional_args", "")

        command = f"semgrep --json --output /tmp/semgrep_results.json"
        if config:
            command += f" --config={config}"
        if additional_args:
            command += f" {additional_args}"
        command += f" {target_path}"

        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in semgrep_scan endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Semgrep Scan Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/bandit", methods=["POST"])
def bandit_scan():
    """Execute Bandit for Python static code analysis."""
    try:
        params = request.json
        target_path = params.get("target_path", ".")
        additional_args = params.get("additional_args", "-r -f json -o /tmp/bandit_results.json")

        command = f"bandit {target_path} {additional_args}"

        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in bandit_scan endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Bandit Scan Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/gdb", methods=["POST"])
def gdb_debug():
    """Execute GDB for debugging binaries."""
    try:
        params = request.json
        filepath = params.get("filepath", "") # Use filepath instead of binary_path
        commands = params.get("commands", []) # List of GDB commands
        additional_args = params.get("additional_args", "")

        if not filepath:
            logger.warning("GDB called without filepath parameter")
            return jsonify({
                "error": "filepath parameter is required"
            }), 400
        
        gdb_command_file = "/tmp/gdb_commands.txt"
        with open(gdb_command_file, "w") as f:
            for cmd in commands:
                f.write(cmd + "\n")
            f.write("quit\n") # Ensure GDB exits
        
        command = f"gdb -q -x {gdb_command_file} {filepath} {additional_args}" # Use filepath here
        result = execute_command_with_check(command)

        try:
            os.remove(gdb_command_file)
        except Exception as e:
            logger.warning(f"Error removing temporary GDB command file: {str(e)}")

        return jsonify(result)
    except Exception as e:
        error_message = f"Error in gdb_debug endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="GDB Debug Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/radare2", methods=["POST"])
def radare2_analyze():
    """Execute Radare2 for binary analysis."""
    try:
        params = request.json
        filepath = params.get("filepath", "") # Use filepath instead of binary_path
        commands = params.get("commands", []) # List of Radare2 commands
        additional_args = params.get("additional_args", "")

        if not filepath:
            logger.warning("Radare2 called without filepath parameter")
            return jsonify({
                "error": "filepath parameter is required"
            }), 400
        
        r2_command_string = ";".join(commands)
        command = f"r2 -q -c \"{r2_command_string}\" {filepath} {additional_args}" # Use filepath here
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in radare2_analyze endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Radare2 Analyze Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/strings", methods=["POST"])
def strings_extract():
    """Extract printable strings from files."""
    try:
        params = request.json
        filepath = params.get("filepath", "") # Use filepath instead of file_path
        additional_args = params.get("additional_args", "")

        if not filepath:
            logger.warning("Strings called without filepath parameter")
            return jsonify({
                "error": "filepath parameter is required"
            }), 400
        
        command = f"strings {filepath} {additional_args}" # Use filepath here
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in strings_extract endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Strings Extract Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/objdump", methods=["POST"])
def objdump_disassemble():
    """Display information from object files (disassemble, view headers, etc.)."""
    try:
        params = request.json
        filepath = params.get("filepath", "") # Use filepath instead of file_path
        additional_args = params.get("additional_args", "-d") # Default to disassemble

        if not filepath:
            logger.warning("Objdump called without filepath parameter")
            return jsonify({
                "error": "filepath parameter is required"
            }), 400
        
        command = f"objdump {additional_args} {filepath}" # Use filepath here
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in objdump_disassemble endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Objdump Disassemble Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/tools/readelf", methods=["POST"])
def readelf_info():
    """Display information about ELF format files."""
    try:
        params = request.json
        filepath = params.get("filepath", "") # Use filepath instead of file_path
        additional_args = params.get("additional_args", "-a") # Default to all info

        if not filepath:
            logger.warning("Readelf called without filepath parameter")
            return jsonify({
                "error": "filepath parameter is required"
            }), 400
        
        command = f"readelf {additional_args} {filepath}" # Use filepath here
        result = execute_command_with_check(command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in readelf_info endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Readelf Info Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        })

@app.route("/api/knowledge_base/read", methods=["POST"])
def read_knowledge_base_category():
    """Reads and returns the content of a specified JSON knowledge base file."""
    try:
        params = request.json
        category = params.get("category", "")

        if not category:
            logger.warning("read_knowledge_base_category called without category parameter")
            return jsonify({"error": "Category parameter is required"}), 400

        knowledge_base_dir = str(KNOWLEDGE_BASE_DIR)
        file_path = os.path.join(knowledge_base_dir, f"{category}.json")

        if not os.path.exists(file_path):
            logger.warning(f"Knowledge base file not found for category: {category}")
            return jsonify({"error": f"Knowledge base file not found for category: {category}"}), 404

        with open(file_path, "r") as f:
            content = json.load(f)
        
        return jsonify(content)

    except Exception as e:
        error_message = f"Error in read_knowledge_base_category endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Read Knowledge Base Category Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/knowledge_base/add", methods=["POST"])
def add_knowledge_base_entry():
    """Adds a new tool or test case to the specified JSON knowledge base file."""
    try:
        params = request.json
        category = params.get("category", "")
        entry_type = params.get("type", "") # "tool" or "test_case"
        entry_data = params.get("data", {}) # The actual tool/test_case data

        if not category or not entry_type or not entry_data:
            logger.warning("add_knowledge_base_entry called with missing parameters")
            return jsonify({"error": "Category, type, and data parameters are required"}), 400

        knowledge_base_dir = str(KNOWLEDGE_BASE_DIR)
        file_path = os.path.join(knowledge_base_dir, f"{category}.json")

        if not os.path.exists(file_path):
            logger.warning(f"Knowledge base file not found for category: {category}. Creating new file.")
            # If file doesn't exist, create a new structure
            knowledge_data = {
                "category_name": category.replace("_", " ").title(),
                "tools": [],
                "test_cases": []
            }
        else:
            with open(file_path, "r") as f:
                knowledge_data = json.load(f)
        
        if entry_type == "tool":
            knowledge_data["tools"].append(entry_data)
        elif entry_type == "test_case":
            knowledge_data["test_cases"].append(entry_data)
        else:
            return jsonify({"error": "Invalid entry type. Must be 'tool' or 'test_case'"}), 400

        with open(file_path, "w") as f:
            json.dump(knowledge_data, f, indent=2)
        
        return jsonify({"message": f"Successfully added {entry_type} to {category} knowledge base."})

    except Exception as e:
        error_message = f"Error in add_knowledge_base_entry endpoint: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="Add Knowledge Base Entry Endpoint")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.route("/api/upload_file", methods=["POST"])
def upload_file():
    """Uploads a file to the /tmp/uploads directory on the server."""
    try:
        if 'file' not in request.files:
            logger.warning("Upload file endpoint called without 'file' in request.files")
            return jsonify({"error": "No file part in the request"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            logger.warning("Upload file endpoint called with empty filename")
            return jsonify({"error": "No selected file"}), 400
        
        if file:
            upload_dir = "/tmp/uploads"
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, file.filename)
            file.save(filepath)
            logger.info(f"File uploaded successfully to: {filepath}")
            return jsonify({"message": "File uploaded successfully", "filepath": filepath}), 200
    except Exception as e:
        error_message = f"Error uploading file: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context="File Upload Endpoint")
        return jsonify({"error": f"Server error during file upload: {str(e)}"}), 500

# Health check endpoint
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    essential_tools = ["nmap", "gobuster", "dirb", "nikto", "sqlmap", "msfconsole", "hydra", "john", "wpscan", "enum4linux"]
    tools_status = {}
    
    for tool in essential_tools:
        try:
            subprocess.run(["which", tool], check=True, capture_output=True)
            tools_status[tool] = True
        except:
            tools_status[tool] = False
    
    all_essential_tools_available = all(tools_status.values())
    
    return jsonify({
        "status": "healthy",
        "message": "HiesenMCP API Server is running",
        "tools_status": tools_status,
        "all_essential_tools_available": all_essential_tools_available
    })

@app.route("/mcp/capabilities", methods=["GET"])
def get_capabilities():
    # This endpoint can be expanded to dynamically list available tools and their parameters
    # For now, we'll return a static list based on the exposed API endpoints
    capabilities = {
        "name": "HiesenMCP API Server",
        "description": "API for executing pentesting tools on a Kali Linux machine.",
        "tools": [
            {"name": "command", "description": "Execute arbitrary shell commands."},
            {"name": "nmap", "description": "Execute Nmap scans."},
            {"name": "gobuster", "description": "Execute Gobuster scans."},
            {"name": "dirb", "description": "Execute Dirb scans."},
            {"name": "nikto", "description": "Execute Nikto scans."},
            {"name": "sqlmap", "description": "Execute SQLMap scans."},
            {"name": "metasploit", "description": "Execute Metasploit modules."},
            {"name": "hydra", "description": "Execute Hydra attacks."},
            {"name": "john", "description": "Execute John the Ripper attacks."},
            {"name": "wpscan", "description": "Execute WPScan analyses."},
            {"name": "enum4linux", "description": "Execute Enum4linux scans."}
        ]
    }
    return jsonify(capabilities)

@app.route("/mcp/tools/kali_tools/<tool_name>", methods=["POST"])
def execute_specific_tool(tool_name):
    # This endpoint can be used for direct tool execution if needed,
    # but for now, we'll route it through the generic command endpoint
    # or call the specific tool functions directly.
    # For simplicity, we'll route it to the generic command endpoint for now.
    try:
        params = request.json
        command_args = params.get("command_args", "")
        full_command = f"{tool_name} {command_args}"
        result = execute_command_with_check(full_command)
        return jsonify(result)
    except Exception as e:
        error_message = f"Error in execute_specific_tool endpoint for {tool_name}: {str(e)}"
        traceback_info = traceback.format_exc()
        logger.error(error_message)
        logger.error(traceback_info)
        _log_error_to_file(error_message, traceback_info, context=f"Execute Specific Tool: {tool_name}")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

def _check_and_download_wordlists():
    """
    Checks for essential wordlist directories and downloads them if not present.
    """
    wordlist_dir = WORDLISTS_DIR
    wordlist_dir.mkdir(parents=True, exist_ok=True)
    
    payloadallthethings_path = wordlist_dir / "PayloadsAllTheThings"
    seclists_path = wordlist_dir / "SecLists"

    if not payloadallthethings_path.exists():
        logger.info(f"PayloadsAllTheThings not found. Cloning into {payloadallthethings_path}...")
        try:
            subprocess.run(
                ["git", "clone", "https://github.com/swisskyrepo/PayloadsAllTheThings.git", str(payloadallthethings_path)],
                check=True,
                capture_output=True,
                text=True
            )
            logger.info("PayloadsAllTheThings cloned successfully.")
        except subprocess.CalledProcessError as e:
            error_message = f"Failed to clone PayloadsAllTheThings: {e}"
            traceback_info = traceback.format_exc()
            logger.error(error_message)
            if e.stderr:
                logger.error(f"Stderr: {e.stderr}")
            _log_error_to_file(error_message, traceback_info, context="Wordlist Download: PayloadsAllTheThings")
        except Exception as e:
            error_message = f"An unexpected error occurred while cloning PayloadsAllTheThings: {e}"
            traceback_info = traceback.format_exc()
            logger.error(error_message)
            _log_error_to_file(error_message, traceback_info, context="Wordlist Download: PayloadsAllTheThings")

    if not seclists_path.exists():
        logger.info(f"SecLists not found. Cloning into {seclists_path}...")
        try:
            subprocess.run(
                ["git", "clone", "https://github.com/danielmiessler/SecLists.git", str(seclists_path)],
                check=True,
                capture_output=True,
                text=True
            )
            logger.info("SecLists cloned successfully.")
        except subprocess.CalledProcessError as e:
            error_message = f"Failed to clone SecLists: {e}"
            traceback_info = traceback.format_exc()
            logger.error(error_message)
            if e.stderr:
                logger.error(f"Stderr: {e.stderr}")
            _log_error_to_file(error_message, traceback_info, context="Wordlist Download: SecLists")
        except Exception as e:
            error_message = f"An unexpected error occurred while cloning SecLists: {e}"
            traceback_info = traceback.format_exc()
            logger.error(error_message)
            _log_error_to_file(error_message, traceback_info, context="Wordlist Download: SecLists")

def main():
    """
    Main entry point for the HiesenMCP server.
    """
    import argparse
    parser = argparse.ArgumentParser(description="Run the HiesenMCP server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host/interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=API_PORT, help=f"Port for the API server (default: {API_PORT})")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    if args.debug:
        app.debug = True
        logger.setLevel(logging.DEBUG)

    _check_and_download_wordlists() # Call wordlist check/download

    logger.info(f"Starting HiesenMCP server on {args.host}:{args.port}...")
    app.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == "__main__":
    main()

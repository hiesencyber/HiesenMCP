#!/usr/bin/env python3

import logging
import sys
from typing import Dict, Any, Optional
import requests
import os

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
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_HIESEN_MCP_SERVER = "http://localhost:1337" # URL of the HiesenMCP server
DEFAULT_REQUEST_TIMEOUT = 300  # 5 minutes default timeout for API requests

class HiesenMCPClient:
    """
    Client for communicating with the HiesenMCP server.
    """
    def __init__(self, server_url: str, timeout: int = DEFAULT_REQUEST_TIMEOUT):
        """
        Initialize the HiesenMCPClient.
        
        Args:
            server_url: URL of the HiesenMCP server.
            timeout: Request timeout in seconds.
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        logger.info(f"Initialized HiesenMCPClient connecting to {server_url}")
        
    def safe_post(self, endpoint: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform a POST request with JSON data.
        
        Args:
            endpoint: API endpoint path (without leading slash).
            json_data: JSON data to send.
            
        Returns:
            Response data as dictionary.
        """
        url = f"{self.server_url}/{endpoint}"
        
        try:
            logger.debug(f"POST {url} with data: {json_data}")
            response = requests.post(url, json=json_data, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            return {"error": f"Request failed: {str(e)}", "success": False}
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return {"error": f"Unexpected error: {str(e)}", "success": False}

    def safe_get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Perform a GET request with optional query parameters.
        
        Args:
            endpoint: API endpoint path (without leading slash)
            params: Optional query parameters
            
        Returns:
            Response data as dictionary
        """
        if params is None:
            params = {}

        url = f"{self.server_url}/{endpoint}"

        try:
            logger.debug(f"GET {url} with params: {params}")
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            return {"error": f"Request failed: {str(e)}", "success": False}
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return {"error": f"Unexpected error: {str(e)}", "success": False}

    def upload_file(self, local_filepath: str) -> Dict[str, Any]:
        """
        Uploads a file to the HiesenMCP server's /tmp/uploads directory.
        
        Args:
            local_filepath: The path to the local file to upload.
            
        Returns:
            A dictionary containing the server's response, including the remote filepath.
        """
        url = f"{self.server_url}/api/upload_file"
        try:
            with open(local_filepath, 'rb') as f:
                files = {'file': (os.path.basename(local_filepath), f)}
                logger.info(f"Uploading file {local_filepath} to {url}")
                response = requests.post(url, files=files, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
        except FileNotFoundError:
            logger.error(f"Local file not found: {local_filepath}")
            return {"error": f"Local file not found: {local_filepath}", "success": False}
        except requests.exceptions.RequestException as e:
            logger.error(f"File upload failed: {str(e)}")
            return {"error": f"File upload failed: {str(e)}", "success": False}
        except Exception as e:
            logger.error(f"Unexpected error during file upload: {str(e)}")
            return {"error": f"Unexpected error during file upload: {str(e)}", "success": False}

    def execute_command(self, command: str) -> Dict[str, Any]:
        """
        Execute a generic command on the HiesenMCP server.
        
        Args:
            command: Command to execute.
            
        Returns:
            Command execution results.
        """
        return self.safe_post("api/command", {"command": command})

    def nmap_scan(self, target: str, scan_type: str = "-sCV", ports: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute an Nmap scan against a target.
        """
        data = {
            "target": target,
            "scan_type": scan_type,
            "ports": ports,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/nmap", data)

    def gobuster_scan(self, url: str, mode: str = "dir", wordlist: str = "/usr/share/wordlists/dirb/common.txt", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Gobuster to find directories, DNS subdomains, or virtual hosts.
        """
        data = {
            "url": url,
            "mode": mode,
            "wordlist": wordlist,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/gobuster", data)

    def dirb_scan(self, url: str, wordlist: str = "/usr/share/wordlists/dirb/common.txt", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Dirb web content scanner.
        """
        data = {
            "url": url,
            "wordlist": wordlist,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/dirb", data)

    def nikto_scan(self, target: str, additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Nikto web server scanner.
        """
        data = {
            "target": target,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/nikto", data)

    def sqlmap_scan(self, url: str, data: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute SQLmap SQL injection scanner.
        """
        post_data = {
            "url": url,
            "data": data,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/sqlmap", post_data)

    def metasploit_run(self, module: str, options: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Execute a Metasploit module.
        """
        data = {
            "module": module,
            "options": options
        }
        return self.safe_post("api/tools/metasploit", data)

    def hydra_attack(self, target: str, service: str, username: str = "", username_file: str = "", password: str = "", password_file: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Hydra password cracking tool.
        """
        data = {
            "target": target,
            "service": service,
            "username": username,
            "username_file": username_file,
            "password": password,
            "password_file": password_file,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/hydra", data)

    def john_crack(self, hash_file: str, wordlist: str = "/usr/share/wordlists/rockyou.txt", format_type: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute John the Ripper password cracker.
        """
        data = {
            "hash_file": hash_file,
            "wordlist": wordlist,
            "format": format_type,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/john", data)

    def wpscan_analyze(self, url: str, additional_args: str = "") -> Dict[str, Any]:
        """
        Execute WPScan WordPress vulnerability scanner.
        """
        data = {
            "url": url,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/wpscan", data)

    def enum4linux_scan(self, target: str, additional_args: str = "-a") -> Dict[str, Any]:
        """
        Execute Enum4linux Windows/Samba enumeration tool.
        """
        data = {
            "target": target,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/enum4linux", data)

    def ffuf_scan(self, url: str, wordlist: str, headers: Dict[str, str] = {}, method: str = "GET", post_data: str = "", match_codes: str = "", filter_codes: str = "", follow_redirects: bool = False, recursion: bool = False, threads: int = 40, mode: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute ffuf for web fuzzing, subdomain enumeration, or directory enumeration.
        """
        data = {
            "url": url,
            "wordlist": wordlist,
            "headers": headers,
            "method": method,
            "post_data": post_data,
            "match_codes": match_codes,
            "filter_codes": filter_codes,
            "follow_redirects": follow_redirects,
            "recursion": recursion,
            "threads": threads,
            "mode": mode,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/ffuf", data)

    def frida_run(self, script: str, target: str, additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Frida with the provided parameters.
        """
        data = {
            "script": script,
            "target": target,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/frida", data)

    def drozer_run(self, command_args: str) -> Dict[str, Any]:
        """
        Execute Drozer with the provided parameters.
        """
        data = {
            "command_args": command_args
        }
        return self.safe_post("api/tools/drozer", data)

    def objection_run(self, gadget: str, command_args: str) -> Dict[str, Any]:
        """
        Execute Objection with the provided parameters.
        """
        data = {
            "gadget": gadget,
            "command_args": command_args
        }
        return self.safe_post("api/tools/objection", data)

    def cycript_run(self, process_id: str = "", script: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Cycript with the provided parameters.
        """
        data = {
            "process_id": process_id,
            "script": script,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/cycript", data)

    def needle_run(self, command_args: str) -> Dict[str, Any]:
        """
        Execute Needle with the provided parameters.
        """
        data = {
            "command_args": command_args
        }
        return self.safe_post("api/tools/needle", data)

    def semgrep_scan(self, target_path: str = ".", config: str = "auto", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Semgrep for static code analysis.
        """
        data = {
            "target_path": target_path,
            "config": config,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/semgrep", data)

    def bandit_scan(self, target_path: str = ".", additional_args: str = "-r -f json -o /tmp/bandit_results.json") -> Dict[str, Any]:
        """
        Execute Bandit for Python static code analysis.
        """
        data = {
            "target_path": target_path,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/bandit", data)

    def gdb_debug(self, filepath: str, commands: list[str] = [], additional_args: str = "") -> Dict[str, Any]:
        """
        Execute GDB for debugging binaries.
        """
        data = {
            "filepath": filepath,
            "commands": commands,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/gdb", data)

    def radare2_analyze(self, filepath: str, commands: list[str] = [], additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Radare2 for binary analysis.
        """
        data = {
            "filepath": filepath,
            "commands": commands,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/radare2", data)

    def strings_extract(self, filepath: str, additional_args: str = "") -> Dict[str, Any]:
        """
        Extract printable strings from files.
        """
        data = {
            "filepath": filepath,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/strings", data)

    def objdump_disassemble(self, filepath: str, additional_args: str = "-d") -> Dict[str, Any]:
        """
        Display information from object files (disassemble, view headers, etc.).
        """
        data = {
            "filepath": filepath,
            "additional_args": additional_args
        }
        return self.safe_post("api/tools/objdump", data)

    def readelf_info(self, filepath: str, additional_args: str = "-a") -> Dict[str, Any]:
        """
        Display information about ELF format files.
        
        Args:
            filepath: Path to the ELF file.
            additional_args: Additional readelf arguments.
            
        Returns:
            ELF information.
        """
        return self.safe_post("api/tools/readelf", data)

    def server_health(self) -> Dict[str, Any]:
        """
        Check the health status of the HiesenMCP API server.
        
        Returns:
            Server health information
        """
        return self.safe_get("health")

    def read_knowledge_base_category(self, category: str) -> Dict[str, Any]:
        """
        Reads and returns the content of a specified JSON knowledge base file from the HiesenMCP server.
        
        Args:
            category: The name of the knowledge base category (e.g., "windows_pentesting").
            
        Returns:
            The content of the knowledge base category as a dictionary.
        """
        return self.safe_post("api/knowledge_base/read", {"category": category})

    def add_knowledge_base_entry(self, category: str, entry_type: str, entry_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adds a new tool or test case to the specified JSON knowledge base file on the HiesenMCP server.
        
        Args:
            category: The name of the knowledge base category (e.g., "windows_pentesting").
            entry_type: The type of entry to add ("tool" or "test_case").
            entry_data: A dictionary containing the data for the tool or test case.
            
        Returns:
            A dictionary containing the server's response.
        """
        data = {
            "category": category,
            "type": entry_type,
            "data": entry_data
        }
        return self.safe_post("api/knowledge_base/add", data)

def setup_hiesen_mcp_client(hiesen_mcp_client: HiesenMCPClient) -> FastMCP:
    """
    Set up the FastMCP client with tool functions to interact with HiesenMCP server.
    """
    mcp = FastMCP("hiesen-mcp-client")
    
    @mcp.tool()
    def execute_remote_command(command: str) -> Dict[str, Any]:
        """
        Execute an arbitrary shell command on the remote HiesenMCP server.
        
        Args:
            command: The shell command string to execute.
            
        Returns:
            A dictionary containing stdout, stderr, return_code, success, timed_out, and partial_results.
        """
        return hiesen_mcp_client.execute_command(command)

    @mcp.tool()
    def upload_file(local_filepath: str) -> Dict[str, Any]:
        """
        Uploads a file from the local filesystem to the remote HiesenMCP server's /tmp/uploads directory.
        
        Args:
            local_filepath: The path to the local file to upload.
            
        Returns:
            A dictionary containing the server's response, including the remote filepath.
        """
        return hiesen_mcp_client.upload_file(local_filepath)

    @mcp.tool()
    def nmap_scan(target: str, scan_type: str = "-sCV", ports: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute an Nmap scan against a target.
        
        Args:
            target: The IP address or hostname to scan
            scan_type: Scan type (e.g., -sV for version detection)
            ports: Comma-separated list of ports or port ranges
            additional_args: Additional Nmap arguments
            
        Returns:
            Scan results
        """
        return hiesen_mcp_client.nmap_scan(target, scan_type, ports, additional_args)

    @mcp.tool()
    def gobuster_scan(url: str, mode: str = "dir", wordlist: str = "/usr/share/wordlists/dirb/common.txt", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Gobuster to find directories, DNS subdomains, or virtual hosts.
        
        Args:
            url: The target URL
            mode: Scan mode (dir, dns, fuzz, vhost)
            wordlist: Path to wordlist file
            additional_args: Additional Gobuster arguments
            
        Returns:
            Scan results
        """
        return hiesen_mcp_client.gobuster_scan(url, mode, wordlist, additional_args)

    @mcp.tool()
    def dirb_scan(url: str, wordlist: str = "/usr/share/wordlists/dirb/common.txt", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Dirb web content scanner.
        
        Args:
            url: The target URL
            wordlist: Path to wordlist file
            additional_args: Additional Dirb arguments
            
        Returns:
            Scan results
        """
        return hiesen_mcp_client.dirb_scan(url, wordlist, additional_args)

    @mcp.tool()
    def nikto_scan(target: str, additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Nikto web server scanner.
        
        Args:
            target: The target URL or IP
            additional_args: Additional Nikto arguments
            
        Returns:
            Scan results
        """
        return hiesen_mcp_client.nikto_scan(target, additional_args)

    @mcp.tool()
    def sqlmap_scan(url: str, data: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute SQLmap SQL injection scanner.
        
        Args:
            url: The target URL
            data: POST data string
            additional_args: Additional SQLmap arguments
            
        Returns:
            Scan results
        """
        return hiesen_mcp_client.sqlmap_scan(url, data, additional_args)

    @mcp.tool()
    def metasploit_run(module: str, options: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Execute a Metasploit module.
        
        Args:
            module: The Metasploit module path
            options: Dictionary of module options
            
        Returns:
            Module execution results
        """
        return hiesen_mcp_client.metasploit_run(module, options)

    @mcp.tool()
    def hydra_attack(target: str, service: str, username: str = "", username_file: str = "", password: str = "", password_file: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Hydra password cracking tool.
        
        Args:
            target: Target IP or hostname
            service: Service to attack (ssh, ftp, http-post-form, etc.)
            username: Single username to try
            username_file: Path to username file
            password: Single password to try
            password_file: Path to password file
            additional_args: Additional Hydra arguments
            
        Returns:
            Attack results
        """
        return hiesen_mcp_client.hydra_attack(target, service, username, username_file, password, password_file, additional_args)

    @mcp.tool()
    def john_crack(hash_file: str, wordlist: str = "/usr/share/wordlists/rockyou.txt", format_type: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute John the Ripper password cracker.
        
        Args:
            hash_file: Path to file containing hashes
            wordlist: Path to wordlist file
            format_type: Hash format type
            additional_args: Additional John arguments
            
        Returns:
            Cracking results.
        """
        return hiesen_mcp_client.john_crack(hash_file, wordlist, format_type, additional_args)

    @mcp.tool()
    def wpscan_analyze(url: str, additional_args: str = "") -> Dict[str, Any]:
        """
        Execute WPScan WordPress vulnerability scanner.
        
        Args:
            url: The target WordPress URL
            additional_args: Additional WPScan arguments
            
        Returns:
            Scan results.
        """
        return hiesen_mcp_client.wpscan_analyze(url, additional_args)

    @mcp.tool()
    def enum4linux_scan(target: str, additional_args: str = "-a") -> Dict[str, Any]:
        """
        Execute Enum4linux Windows/Samba enumeration tool.
        
        Args:
            target: The target IP or hostname
            additional_args: Additional enum4linux arguments
            
        Returns:
            Enumeration results.
        """
        return hiesen_mcp_client.enum4linux_scan(target, additional_args)

    @mcp.tool()
    def ffuf_scan(url: str, wordlist: str, headers: Dict[str, str] = {}, method: str = "GET", post_data: str = "", match_codes: str = "", filter_codes: str = "", follow_redirects: bool = False, recursion: bool = False, threads: int = 40, mode: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute ffuf for web fuzzing, subdomain enumeration, or directory enumeration.
        
        Args:
            url: The target URL.
            wordlist: Path to wordlist file.
            headers: Dictionary of HTTP headers.
            method: HTTP method to use (default: GET).
            post_data: POST data string.
            match_codes: Comma-separated list of HTTP status codes to match.
            filter_codes: Comma-separated list of HTTP status codes to filter.
            follow_redirects: Follow redirects (default: False).
            recursion: Scan recursively (default: False).
            threads: Number of concurrent threads (default: 40).
            mode: FFUF mode (e.g., clusterbomb, pitchfork).
            additional_args: Additional FFUF arguments.
            
        Returns:
            Scan results.
        """
        return hiesen_mcp_client.ffuf_scan(url, wordlist, headers, method, post_data, match_codes, filter_codes, follow_redirects, recursion, threads, mode, additional_args)

    @mcp.tool()
    def frida_run(script: str, target: str, additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Frida with the provided parameters.
        
        Args:
            script: Path to the Frida script.
            target: The target process name or PID.
            additional_args: Additional Frida arguments.
            
        Returns:
            Execution results.
        """
        return hiesen_mcp_client.frida_run(script, target, additional_args)

    @mcp.tool()
    def drozer_run(command_args: str) -> Dict[str, Any]:
        """
        Execute Drozer with the provided parameters.
        
        Args:
            command_args: Drozer command arguments (e.g., "agent discover").
            
        Returns:
            Execution results.
        """
        return hiesen_mcp_client.drozer_run(command_args)

    @mcp.tool()
    def objection_run(gadget: str, command_args: str) -> Dict[str, Any]:
        """
        Execute Objection with the provided parameters.
        
        Args:
            gadget: The target application package name or PID.
            command_args: Objection command arguments (e.g., "android sslpinning disable").
            
        Returns:
            Execution results.
        """
        return hiesen_mcp_client.objection_run(gadget, command_args)

    @mcp.tool()
    def cycript_run(process_id: str = "", script: str = "", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Cycript with the provided parameters.
        
        Args:
            process_id: The target process ID.
            script: Path to the Cycript script or inline script.
            additional_args: Additional Cycript arguments.
            
        Returns:
            Execution results.
        """
        return hiesen_mcp_client.cycript_run(process_id, script, additional_args)

    @mcp.tool()
    def needle_run(command_args: str) -> Dict[str, Any]:
        """
        Execute Needle with the provided parameters.
        
        Args:
            command_args: Needle command arguments (e.g., "ios scanner --modules").
            
        Returns:
            Execution results.
        """
        return hiesen_mcp_client.needle_run(command_args)

    @mcp.tool()
    def semgrep_scan(target_path: str = ".", config: str = "auto", additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Semgrep for static code analysis.
        
        Args:
            target_path: The path to the code to scan.
            config: Semgrep configuration (e.g., "auto", "p/python").
            additional_args: Additional Semgrep arguments.
            
        Returns:
            Scan results.
        """
        return hiesen_mcp_client.semgrep_scan(target_path, config, additional_args)

    @mcp.tool()
    def bandit_scan(target_path: str = ".", additional_args: str = "-r -f json -o /tmp/bandit_results.json") -> Dict[str, Any]:
        """
        Execute Bandit for Python static code analysis.
        
        Args:
            target_path: The path to the Python code to scan.
            additional_args: Additional Bandit arguments.
            
        Returns:
            Scan results.
        """
        return hiesen_mcp_client.bandit_scan(target_path, additional_args)

    @mcp.tool()
    def gdb_debug(filepath: str, commands: list[str] = [], additional_args: str = "") -> Dict[str, Any]:
        """
        Execute GDB for debugging binaries.
        
        Args:
            filepath: Path to the binary to debug.
            commands: List of GDB commands to execute.
            additional_args: Additional GDB arguments.
            
        Returns:
            Debugging results.
        """
        return hiesen_mcp_client.gdb_debug(filepath, commands, additional_args)

    @mcp.tool()
    def radare2_analyze(filepath: str, commands: list[str] = [], additional_args: str = "") -> Dict[str, Any]:
        """
        Execute Radare2 for binary analysis.
        
        Args:
            filepath: Path to the binary to analyze.
            commands: List of Radare2 commands to execute.
            additional_args: Additional Radare2 arguments.
            
        Returns:
            Analysis results.
        """
        return hiesen_mcp_client.radare2_analyze(filepath, commands, additional_args)

    @mcp.tool()
    def strings_extract(filepath: str, additional_args: str = "") -> Dict[str, Any]:
        """
        Extract printable strings from files.
        
        Args:
            filepath: Path to the file.
            additional_args: Additional strings arguments.
            
        Returns:
            Extracted strings.
        """
        return hiesen_mcp_client.strings_extract(filepath, additional_args)

    @mcp.tool()
    def objdump_disassemble(filepath: str, additional_args: str = "-d") -> Dict[str, Any]:
        """
        Display information from object files (disassemble, view headers, etc.).
        
        Args:
            filepath: Path to the object file.
            additional_args: Additional objdump arguments.
            
        Returns:
            Disassembly or information.
        """
        return hiesen_mcp_client.objdump_disassemble(filepath, additional_args)

    @mcp.tool()
    def readelf_info(filepath: str, additional_args: str = "-a") -> Dict[str, Any]:
        """
        Display information about ELF format files.
        
        Args:
            filepath: Path to the ELF file.
            additional_args: Additional readelf arguments.
            
        Returns:
            ELF information.
        """
        return hiesen_mcp_client.readelf_info(filepath, additional_args)

    @mcp.tool()
    def server_health() -> Dict[str, Any]:
        """
        Check the health status of the HiesenMCP API server.
        
        Returns:
            Server health information
        """
        return hiesen_mcp_client.server_health()

    @mcp.tool()
    def read_knowledge_base_category(category: str) -> Dict[str, Any]:
        """
        Reads and returns the content of a specified JSON knowledge base file from the HiesenMCP server.
        
        Args:
            category: The name of the knowledge base category (e.g., "windows_pentesting").
            
        Returns:
            The content of the knowledge base category as a dictionary.
        """
        return hiesen_mcp_client.read_knowledge_base_category(category)

    @mcp.tool()
    def add_knowledge_base_entry(category: str, entry_type: str, entry_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adds a new tool or test case to the specified JSON knowledge base file on the HiesenMCP server.
        
        Args:
            category: The name of the knowledge base category (e.g., "windows_pentesting").
            entry_type: The type of entry to add ("tool" or "test_case").
            entry_data: A dictionary containing the data for the tool or test case.
            
        Returns:
            A dictionary containing the server's response.
        """
        return hiesen_mcp_client.add_knowledge_base_entry(category, entry_type, entry_data)

    return mcp

def main():
    """
    Main entry point for the HiesenMCP client.
    """
    import argparse
    parser = argparse.ArgumentParser(description="Run the HiesenMCP client")
    parser.add_argument("--server", type=str, default=DEFAULT_HIESEN_MCP_SERVER,
                        help=f"HiesenMCP server URL (default: {DEFAULT_HIESEN_MCP_SERVER})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_REQUEST_TIMEOUT,
                        help=f"Request timeout in seconds (default: {DEFAULT_REQUEST_TIMEOUT})")
    args = parser.parse_args()

    hiesen_mcp_client = HiesenMCPClient(args.server, args.timeout)
    mcp = setup_hiesen_mcp_client(hiesen_mcp_client)
    logger.info("Starting HiesenMCP client...")
    mcp.run()

if __name__ == "__main__":
    main()

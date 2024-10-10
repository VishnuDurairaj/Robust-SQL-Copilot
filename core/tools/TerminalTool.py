import sys
sys.dont_write_bytecode =True

import platform
import subprocess
import threading
import time
from typing import List, Dict, Any
from pydantic import BaseModel, Field

class ExecuteTerminalCommand(BaseModel):
    """
    Use this tool to execute terminal commands with safety checks, compatible with Windows.
    """
    reasoning: List[str] = Field(description="Why you are using this tool")
    
    command: str = Field(
        ..., description="The terminal command to execute."
    )
    args: List[str] = Field(
        default=[], description="A list of arguments to pass to the command."
    )

    def run(self, idle_threshold: int = 100) -> Dict[str, Any]:
        # Safety check for harmful commands
        if not self.is_safe_command():
            return {
                "status": "error",
                "message": "The command was identified as potentially harmful and will not be executed."
            }

        def target(result_dict: Dict[str, str]):
            try:
                # Combine command and arguments
                command_with_args = [self.command] + self.args
                
                # Run the command using subprocess
                result = subprocess.Popen(
                    command_with_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=True  # Use shell=True to allow execution of shell commands
                )
                
                stdout, stderr = result.communicate()
                
                result_dict["stdout"] = stdout
                result_dict["stderr"] = stderr
                result_dict["status"] = "completed"
                
            except subprocess.CalledProcessError as e:
                result_dict["status"] = "error"
                result_dict["stderr"] = e.stderr
            except Exception as e:
                result_dict["status"] = "error"
                result_dict["stderr"] = str(e)

        result_dict = {"stdout": "", "stderr": "", "status": "running"}
        thread = threading.Thread(target=target, args=(result_dict,))
        thread.start()

        idle = 0
        previous_stdout = ""
        
        while thread.is_alive():
            time.sleep(1)  # Small delay to wait for output
            
            # Check if there is any new output
            if result_dict["stdout"] != previous_stdout:
                previous_stdout = result_dict["stdout"]
                idle = 0
            else:
                idle += 1
            
            if idle > idle_threshold:
                result_dict["stderr"] += "\nExecution appears to be idle, but the process is still running."
                break

        # Do not block, just return the current state and allow the thread to continue running
        return result_dict

    def is_safe_command(self):
        """
        Checks if the command is safe to execute. Adjusts checks based on the operating system.
        """
        # Platform-specific dangerous commands
        if platform.system() == "Windows":
            dangerous_commands = ["del", "rmdir", "shutdown", "taskkill", "format", "diskpart", "attrib"]
        else:
            dangerous_commands = ["rm", "dd", "mkfs", "shutdown", "reboot", "kill", "pkill", "sudo", "chmod", "chown", "mv", "rmdir"]

        dangerous_patterns = [";", "&&", "|", ">", "<"]

        # Check for dangerous commands
        if any(dangerous in self.command for dangerous in dangerous_commands):
            return False
        
        # Check for dangerous patterns in the command
        if any(pattern in self.command for pattern in dangerous_patterns):
            return False

        return True

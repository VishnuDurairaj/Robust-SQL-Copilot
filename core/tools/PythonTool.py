import sys
sys.dont_write_bytecode =True

import io
import sys
import time
import threading
import subprocess
import pandas as pd
from typing import List,Dict,Any
from pydantic import BaseModel, Field

class RunPythonFile(BaseModel):
    """
    Use this tool to execute a Python file and return the output.
    """
    reasoning: List[str] = Field(description="Why you are using this tool")

    file_name: str = Field(
        ..., description="Python file name to run."
    )

    def run(self) -> Dict[str, Any]:
        if not self.file_name.endswith('.py'):
            return {"status": "error", "message": f"Error: The file '{self.file_name}' does not have a .py extension. Only Python files are allowed."}
        
        return self.run_python_file()

    def run_python_file(self) -> Dict[str, Any]:
        """
        Run a Python file using subprocess.Popen with idle detection.
        """
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()

        def target():
            try:
                with open(self.file_name, "r") as file:
                    exec(file.read(), globals())
            except Exception as e:
                print("Error: ",e)
                sys.stderr.write(str(e))
        
        thread = threading.Thread(target=target)
        thread.start()

        idle = 0
        full_output = ""
        errors = ""

        while thread.is_alive():
            time.sleep(1)  # Small delay to wait for output

            # Read the current output
            current_output = sys.stdout.getvalue()
            if current_output != full_output:
                full_output = current_output
                idle = 0
            else:
                idle += 1

            if idle > 100:
                errors = "Script execution appears to be idle, but the process is still running."
                break

        # Wait for the thread to complete
        # thread.join()

        # Restore original stdout and stderr
        sys.stdout = old_stdout
        sys.stderr = old_stderr

        return {
            "status": "running" if thread.is_alive() else "completed",
            "output": full_output,
            "errors": errors
        }

class ExecutePythonScript(BaseModel):
    "Use this tool to execute and print a python script"
    
    python_script: str = Field(description="Python script to execute. Make sure to use print statements to display the output of specific variables or results.")
    
    def run(self, idle_threshold: int = 100) -> Dict[str, Any]:
        # Capture the output of the script
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        
        def target():
            try:
                exec(self.python_script)
            except Exception as e:
                print(f"************************ Eror: {e}")
                sys.stderr.write(str(e))
        
        thread = threading.Thread(target=target)
        thread.start()

        idle = 0
        full_output = ""
        errors = ""
        
        while thread.is_alive():
            time.sleep(1)  # Small delay to wait for output
            
            # Read the current output
            current_output = sys.stdout.getvalue()
            if current_output != full_output:
                full_output = current_output
                idle = 0
            else:
                idle += 1
            
            if idle > idle_threshold:
                errors = "Script execution appears to be idle, but the process is still running."
                break
        
        # Do not block, just return the current state and allow the thread to continue running
        sys.stdout = old_stdout
        sys.stderr = old_stderr

        return {
            "status": "running" if thread.is_alive() else "completed",
            "output": full_output,
            "errors": errors
        }
    
class InstallPythonPackage(BaseModel):
    """
    Use this tool to install Python packages using pip.
    """
    reasoning :List[str] = Field(description="Why you are using this tool")

    package_name: str = Field(
        ..., description="The name of the Python package to install."
    )

    def run(self):
        try:
            # Run pip install using subprocess
            result = subprocess.run(
                ["pip", "install", self.package_name],
                capture_output=True,
                text=True,
                check=True
            )
            return f"Package '{self.package_name}' installed successfully. Output:\n{result.stdout}"
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.strip().split('\n')[-1]  # Capture the exact error message
            return f"An error occurred while installing the package '{self.package_name}': {error_message}"
        except Exception as e:
            return f"An unexpected error occurred: {str(e)}"

class LoadExcelFile(BaseModel):
    """
    Use this tool to load a CSV or Excel file and return the first 5 rows.
    """
    reasoning :List[str] = Field(description="Why you are using this tool")
    
    file_name: str = Field(
        ..., description="CSV or Excel file name to load."
    )

    def run(self):
        # Check if the file has a .csv or .xlsx extension
        if not (self.file_name.endswith('.csv') or self.file_name.endswith('.xlsx')):
            return f"Error: The file '{self.file_name}' does not have a .csv or .xlsx extension. Only CSV and Excel files are allowed."

        try:
            # Load the data file using pandas
            if self.file_name.endswith('.csv'):
                data = pd.read_csv(self.file_name)
            else:
                data = pd.read_excel(self.file_name)

            # Get the first 5 rows
            first_5_rows = data.head().to_markdown(index=False)
            return f"First 5 rows of the file '{self.file_name}':\n\n{first_5_rows}"
        except Exception as e:
            return f"An error occurred while loading the file: {str(e)}"

# tools = prepare_schema_from_tool([SaveFile,RunPythonFile,ReadFile,InstallPythonPackage])
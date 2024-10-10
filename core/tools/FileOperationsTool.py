import sys
sys.dont_write_bytecode =True

import os
import shutil
from pydantic import BaseModel, Field
from typing import List

class SaveFile(BaseModel):
    """
    Use this tool to save content to a file.
    """
    reasoning :List[str] = Field(description="Why you are using this tool")

    file_content: str = Field(
        ..., description="File content to save."
    )
    file_path: str = Field(
        ..., description="File path with proper extension."
    )

    def run(self):
        with open(self.file_path, "w") as f:
            f.write(self.file_content)
        return f"File saved successfully. File name: {self.file_path}"
    
class ReadTextFile(BaseModel):
    """
    Use this tool to read the content of a text file. 
    """
    reasoning :List[str] = Field(description="Why you are using this tool")

    file_name: str = Field(
        ..., description="File name to read."
    )

    def run(self):
        try:
            if self.file_name.endswith((".csv","xlsx")):
                return "To read a excel file you need to write a python script. This tool is just to read text files."
            with open(self.file_name, "r") as file:
                content = file.read()
            return content
        except FileNotFoundError:
            return f"File not found: {self.file_name}"
        except Exception as e:
            return f"An error occurred while reading the file: {str(e)}"


class AppendToFile(BaseModel):
    """
    Use this tool to append content to an existing file.
    """
    reasoning :List[str] = Field(description="Why you are using this tool")

    file_name: str = Field(..., description="File name to append to.")
    content: str = Field(..., description="Content to append.")

    def run(self):
        try:
            with open(self.file_name, "a") as file:
                file.write(self.content)
            return f"Content appended to file: {self.file_name}"
        except Exception as e:
            return f"An error occurred while appending to the file: {str(e)}"


class DeleteFile(BaseModel):
    """
    Use this tool to delete a specified file.
    """
    reasoning :List[str] = Field(description="Why you are using this tool")

    file_name: str = Field(..., description="File name to delete.")

    def run(self):
        try:
            os.remove(self.file_name)
            return f"File deleted successfully: {self.file_name}"
        except FileNotFoundError:
            return f"File not found: {self.file_name}"
        except Exception as e:
            return f"An error occurred while deleting the file: {str(e)}"


class ListFilesInDirectory(BaseModel):
    """
    Use this tool to list all files in a specified directory.
    """
    reasoning :List[str] = Field(description="Why you are using this tool")

    directory: str = Field(..., description="Directory to list files from.")

    def run(self):
        try:
            files = os.listdir(self.directory)
            return str(files)
        except FileNotFoundError:
            return f"Directory not found: {self.directory}"
        except Exception as e:
            return f"An error occurred while listing files: {str(e)}"


class MoveFile(BaseModel):
    """
    Use this tool to move a file from one location to another.
    """
    reasoning :List[str] = Field(description="Why you are using this tool")
    source: str = Field(..., description="Source file path.")
    destination: str = Field(..., description="Destination file path.")

    def run(self):
        try:
            shutil.move(self.source, self.destination)
            return f"File moved from {self.source} to {self.destination}"
        except FileNotFoundError:
            return f"File not found: {self.source}"
        except Exception as e:
            return f"An error occurred while moving the file: {str(e)}"


class CopyFile(BaseModel):
    """
    Use this tool to copy a file from one location to another.
    """
    reasoning :List[str] = Field(description="Why you are using this tool")
    source: str = Field(..., description="Source file path.")
    destination: str = Field(..., description="Destination file path.")

    def run(self):
        try:
            shutil.copy(self.source, self.destination)
            return f"File copied from {self.source} to {self.destination}"
        except FileNotFoundError:
            return f"File not found: {self.source}"
        except Exception as e:
            return f"An error occurred while copying the file: {str(e)}"


class GetAvailableFilesandFolders(BaseModel):
    """
    Use this tool to get all the available files and folders starting from a given directory.
    """
    reasoning :List[str] = Field(description="Why you are using this tool")

    directory: str = Field(..., description="Starting directory to get the project structure from.",examples=[".","/project"])

    def run(self):
        try:
            project_structure = ""
            for root, dirs, files in os.walk(self.directory):
                level = root.replace(self.directory, '').count(os.sep)
                indent = ' ' * 4 * level
                project_structure += f"{indent}{os.path.basename(root)}/\n"
                sub_indent = ' ' * 4 * (level + 1)
                for f in files:
                    project_structure += f"{sub_indent}{f}\n"
            return project_structure
        except FileNotFoundError:
            return f"Directory not found: {self.directory}"
        except Exception as e:
            return f"An error occurred while getting the project structure: {str(e)}"


class CreateFolder(BaseModel):
    """
    Use this tool to create a new folder.
    """
    reasoning :List[str] = Field(description="Why you are using this tool")

    folder_path: str = Field(..., description="Path of the folder to create.")

    def run(self):
        try:
            os.makedirs(self.folder_path, exist_ok=True)
            return f"Folder created successfully: {self.folder_path}"
        except Exception as e:
            return f"An error occurred while creating the folder: {str(e)}"


class DeleteFolder(BaseModel):
    """
    Use this tool to delete a specified folder and its contents.
    """
    reasoning :List[str] = Field(description="Why you are using this tool")

    folder_path: str = Field(..., description="Path of the folder to delete.")

    def run(self):
        try:
            shutil.rmtree(self.folder_path)
            return f"Folder deleted successfully: {self.folder_path}"
        except FileNotFoundError:
            return f"Folder not found: {self.folder_path}"
        except Exception as e:
            return f"An error occurred while deleting the folder: {str(e)}"


class MoveFolder(BaseModel):
    """
    Use this tool to move a folder from one location to another.
    """
    reasoning :List[str] = Field(description="Why you are using this tool")
    source: str = Field(..., description="Source folder path.")
    destination: str = Field(..., description="Destination folder path.")

    def run(self):
        try:
            shutil.move(self.source, self.destination)
            return f"Folder moved from {self.source} to {self.destination}"
        except FileNotFoundError:
            return f"Folder not found: {self.source}"
        except Exception as e:
            return f"An error occurred while moving the folder: {str(e)}"

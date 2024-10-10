import sys
sys.dont_write_bytecode = True

import os
import uuid
import json
import shutil
import requests
import datetime
from typing import List
from pydantic import BaseModel, Field
from websocket import create_connection, WebSocketException
import plotly.graph_objects as go  # Import Plotly

class NotebookManager:

    def __init__(self,session_id=None):
        self.host = os.environ.get('JUPYTER_URL', 'localhost:8888')
        # self.host = "localhost:8888"

        self.headers = {
            'Content-Type': 'application/json'
        }
        self.notebooks_created = []
        self.session_id = session_id

        if not self.session_id:
            self.session_id = str(uuid.uuid4())
        self.create_notebook()
        self.kernel_id = None  # Store the kernel ID here

    def _initialize_kernel(self):
        # Initialize the kernel if it hasn't been initialized yet
        if not self.kernel_id:
            response = requests.post(f"http://{self.host}/api/kernels", headers=self.headers)
            if response.status_code != 201:
                raise Exception('Failed to start kernel')
            self.kernel_id = response.json()['id']
        return self.kernel_id

    def delete_notebook(self, notebook_name):
        response = requests.delete(f"http://{self.host}/api/contents/{notebook_name}.ipynb", headers=self.headers)
        if response.status_code == 204:
            print(f"Notebook {notebook_name}.ipynb deleted successfully.")
            self.notebooks_created.remove(notebook_name)
            # Add this code to remove the .Trash-0 folder
            project_root = os.path.abspath(os.getcwd())  # Assuming the current working directory is already 'Production-Agent'
            trash_path = os.path.join(project_root, r".Trash-0")
            ipy_path = os.path.join(project_root, r".ipynb_checkpoints")

            if os.path.exists(trash_path):
                shutil.rmtree(trash_path)
                shutil.rmtree(ipy_path)
        else:
            print(f"Failed to delete notebook {notebook_name}.ipynb. Status code: {response.status_code}")

    def __del__(self):
        # Delete all created notebooks when the object is destroyed
        for notebook_name in self.notebooks_created:
            self.delete_notebook(notebook_name)

    def create_notebook(self):
        data = {"type": "notebook", "path": "/notebooks"}
        response = requests.post(f"http://{self.host}/api/contents", headers=self.headers, data=json.dumps(data))
        if response.status_code == 201:
            previous_file_name = response.json()["path"]
            filename = {"path": f"/{self.session_id}.ipynb"}
            response = requests.patch(f"http://{self.host}/api/contents/{previous_file_name}", headers=self.headers, data=json.dumps(filename))
            if response.status_code == 200:
                self.notebooks_created.append(self.session_id)
                return self.session_id
        raise Exception('Failed to create notebook')

    def add_code_cell(self, notebook_name, code):
        response = requests.get(f"http://{self.host}/api/contents/{notebook_name}.ipynb", headers=self.headers)
        if response.status_code != 200:
            raise Exception('Failed to fetch notebook content')

        file = response.json()
        new_cell = {
            'cell_type': 'code',
            'metadata': {},
            'execution_count': None,
            'source': code,
            'outputs': []
        }
        file['content']['cells'].append(new_cell)
        response = requests.put(f"http://{self.host}/api/contents/{notebook_name}.ipynb", headers=self.headers, data=json.dumps(file))
        if response.status_code == 200:
            return True
        raise Exception('Failed to save notebook')

    def execute_code(self, notebook_name):
        try:
            kernel_id = self._initialize_kernel()
            
            response = requests.get(f"http://{self.host}/api/contents/{notebook_name}.ipynb", headers=self.headers)
            if response.status_code != 200:
                raise Exception('Failed to fetch notebook content')
            
            file = response.json()
            cells = file['content']['cells'][-1]
            
            outputs = []
            ws = create_connection(f"ws://{self.host}/api/kernels/{kernel_id}/channels")
            
            try:
                for cell in [cells]:
                    if cell['cell_type'] == 'code' and cell['source']:
                        code = cell['source']
                        execute_request_msg = self._send_execute_request(code)
                        ws.send(json.dumps(execute_request_msg))

                        execution_done = False
                        while not execution_done:
                            try:
                                rsp = json.loads(ws.recv())
                                msg_type = rsp["msg_type"]
                                parent_msg_id = rsp.get("parent_header", {}).get("msg_id", None)
                                if parent_msg_id == execute_request_msg['header']['msg_id']:

                                    if msg_type == "execute_result":
                                        # with open("execute_result.txt","w") as f:
                                        #     f.write(str(rsp))
                                        if 'application/vnd.plotly.v1+json' in rsp["content"]["data"].keys():

                                            result = {
                                                "data": rsp["content"]["data"]["application/vnd.plotly.v1+json"],
                                                "output_type": "plotly",
                                            }

                                            outputs.append(result)


                                        elif 'image/png' in rsp["content"]["data"].keys():
                                                                    
                                            result = {
                                                "data": f"\n![image](data:image/png;base64,{rsp['content']['data']['image/png']})\n",
                                                "output_type": "image",
                                            }
                                            outputs.append(result)
                                            
                                        else:
                                            result = {
                                                "data": rsp["content"]["data"]['text/plain'],
                                                "output_type": "execute_result",
                                                "metadata": {}
                                            }
                                            outputs.append(result)

                                    elif msg_type == 'display_data':
                                        # print("display_data: ")

                                        if 'application/vnd.plotly.v1+json' in rsp["content"]["data"].keys():

                                            result = {
                                                "data": rsp["content"]["data"]["application/vnd.plotly.v1+json"],
                                                "output_type": "plotly",
                                            }

                                            outputs.append(result)


                                        elif 'image/png' in rsp["content"]["data"].keys():
                                                                    
                                            result = {
                                                "data": f"\n![image](data:image/png;base64,{rsp['content']['data']['image/png']})\n",
                                                "output_type": "image",
                                            }

                                            outputs.append(result)

                                    elif msg_type == "stream":
                                        # print("res: ",rsp)

                                        result = {
                                            "name": rsp["content"]["name"],
                                            "output_type": "stream",
                                            "data": rsp["content"]["text"]
                                        }
                                        if len(outputs):
                                            if outputs[-1]['output_type'] == 'stream':
                                                outputs[-1]['data']+="\n"+result['data']
                                        else:
                                            outputs.append(result)

                                    elif msg_type == "error":
                                        # print("res: ",rsp)

                                        result = {
                                            "output_type": "error",
                                            "ename": rsp["content"]["ename"],
                                            "evalue": rsp["content"]["evalue"],
                                            "data":rsp["content"]['ename']+":"+rsp["content"]['evalue'],
                                            "traceback": rsp["content"]["traceback"]
                                        }
                                        outputs.append(result)
                                        execution_done = True  # Stop on error

                                    elif msg_type == "execute_reply" and rsp["content"]["status"] == "ok":

                                        execution_done = True

                                    # When status is 'idle' and msg_type is 'status', execution is done
                                    elif msg_type == "status" and rsp["content"]["execution_state"] == "idle":

                                        execution_done = True

                            except (json.JSONDecodeError, WebSocketException) as e:
                                raise Exception(f'Error while receiving WebSocket message: {e}')

                # Save the outputs to the notebook
                # file['content']['cells'][-1]['outputs'] = outputs[-1]
                # response = requests.put(f"http://{self.host}/api/contents/{notebook_name}.ipynb", headers=self.headers, data=json.dumps(file))
                # if response.status_code != 200:
                #     raise Exception('Failed to save notebook outputs')
                
                return outputs

            finally:
                ws.close()

        except Exception as e:
            print(f"An error occurred: {e}")
            return []

    def _send_execute_request(self, code):
        msg_type = 'execute_request'
        content = {'code': code, 'silent': False}
        hdr = {
            'msg_id': uuid.uuid1().hex,
            'username': 'test',
            'session': uuid.uuid1().hex,
            'data': datetime.datetime.now().isoformat(),
            'msg_type': msg_type,
            'version': '5.0'
        }
        msg = {
            'header': hdr,
            'parent_header': hdr,
            'metadata': {},
            'content': content
        }
        return msg

    def run_code(self, code):
        if not self.session_id:
            self.session_id = str(uuid.uuid4())
            self.create_notebook()
        
        self.add_code_cell(self.session_id, code)
        outputs = self.execute_code(self.session_id)

        if not len(outputs):
            print(f"Jupyter Trying Again : {outputs}")
            outputs = self.execute_code(self.session_id)
            print(f"Done......")

        # Apply the standardize_output method to each output

        if len(outputs):
            standardized_outputs = [self.standardize_output(output) for output in outputs]

            return standardized_outputs
        else:
            return []
    
        # return {"output": outputs}

    def standardize_output(self, output):
        standardized_output = {
            "output_type": output.get('output_type', 'unknown'),
            "output": None,
            "final_output":None,
            "display_type":"text"
        }

        # Check if output is from a print statement (text stream)
        if output.get('output_type') == 'stream' and output.get('name') == 'stdout':
            standardized_output["output"] = output.get('data', '').strip()
            standardized_output["final_output"] = output.get('data', '').strip()
            standardized_output["display_type"] = "text"
        # Check if output is a rich object like a DataFrame or Plotly chart
        elif output.get('output_type') == 'execute_result':

            standardized_output["output"] = output.get('data')
            standardized_output["final_output"] = output.get('data')
            standardized_output["display_type"] = "text"

        elif output.get('output_type') == 'display_data':
            standardized_output["output"] = output.get('data')
            standardized_output["final_output"] = output.get('data')
            standardized_output["display_type"] = "text"

        elif output.get('output_type') == 'plotly':
            standardized_output["output"] = output.get('data')
            standardized_output["final_output"] = "The graph has been generated"
            standardized_output["display_type"] = "plotly"

        elif output.get('output_type') == 'image':
            standardized_output["output"] = output.get('data')
            standardized_output["final_output"] = "The image has been generated"
            standardized_output["display_type"] = "image"

        # Check if output is an error
        elif output.get('output_type') == 'error':
            standardized_output["output"] = f"Error: {output.get('ename', '')}: {output.get('evalue', '')}."
            standardized_output["final_output"] =  f"Error: {output.get('ename', '')}: {output.get('evalue', '')}."
            standardized_output["display_type"] = "error"

        elif output.get('output_type') == 'execute_reply':
            standardized_output["output"] = output.get('text', '').strip()
            standardized_output["final_output"] = output.get('text', '').strip()
            standardized_output["display_type"] = "text"

        # Default to raw output if no specific format is detected
        if standardized_output["output"] is None:
            standardized_output["output"] = str(output).strip()
            standardized_output["final_output"] = str(output).strip()

        return standardized_output

# notebookmanager = NotebookManager()

# class JupyterNotebookTool(BaseModel):

#     """A tool for executing Python code in a stateful Jupyter notebook environment."""
    
#     python_code: str = Field(description="A valid python code to execute in a new jupyter notebook cell")

#     # expected_output_type : List[str] = Field(description="What output type should the script produce? It might be a single output or a combination of these: [text, dataframe, plotly chart, image, log or nothing]. Please specify the expected output(s) type in the exact order they should appear")

#     def run(self):

#         result = notebookmanager.run_code(self.python_code)

#         return result

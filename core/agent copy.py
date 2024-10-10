# -------------------------------- Structured Agent -------------------------------------

import json
import asyncio
from enum import Enum
from typing import List,Type
from core.helper import print_colored
from pydantic import BaseModel,Field

class StructuredAgent:

    def __init__(self,model,agent_name,agent_description,agent_instructions,tools=[],assistant_agents=[],max_allowed_attempts=10,verbose=True) -> None:
        self.model = model 
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.agent_instructions=agent_instructions
        self.tools = tools
        self.assistant_agents = assistant_agents
        self.tool_names = []
        self.max_allowed_attempts= max_allowed_attempts
        self.attempts_made = 0
        self.messages = []
        self.verbose = verbose
        self.input_tokens = 0
        self.output_tokens = 0

        if len(self.assistant_agents):

            self.prepare_prompt()
            self.agents_as_tools = {agent.agent_name:agent for agent in assistant_agents}
            self.assistants_names = []

        self.response_format = self.prepare_Default_tools()

        if len(self.tools):

            self.tool_objects = {i:j for i,j in zip(self.tool_names,tools)}

            tool_schemas = self.prepare_schema_from_tool(self.tools)
            self.agent_instructions+="""\n## Available Tools:\n"""
            self.agent_instructions+=f"""\nYou have access to the following tools:\n{tool_schemas}\nYou must use one of these tools to answer the user's question.\n\n"""
            self.agent_instructions+="""IMPORTANT!: You must provide your response in the below json format.
{
"thoughts":["Always you should think before taking any action"],
"tool_name":"Name of the tool",
"tool_args":{"arg_name":"arg_value"}
}
"""
        
    def prepare_Default_tools(self):

        # Prepare final answer tool
        class FinalAnswer(BaseModel):
            final_answer : str = Field(description="Your final response to the user")
            def run(self):
                return self.final_answer
    
        self.tools.append(FinalAnswer)

        # Prepare Assign Task tool
        if len(self.assistant_agents):

            self.assistants_names = [i.agent_name for i in self.assistant_agents]

            recipients = Enum("recipient", {name: name for name in self.assistants_names})

            assistant_description = f"Choose the right agent to assign the task: {self.assistants_names}\n\n"

            for assistant in self.assistant_agents:

                assistant_description+=assistant.agent_name+" : "+assistant.agent_description+"\n"

            class AssignTask(BaseModel):

                """Use this tool to facilitate direct, synchronous communication between specialized agents within your agency. When you send a message using this tool, you receive a response exclusively from the designated recipient agent. To continue the dialogue, invoke this tool again with the desired recipient agent and your follow-up message. Remember, communication here is synchronous; the recipient agent won't perform any tasks post-response. You are responsible for relaying the recipient agent's responses back to the user, as the user does not have direct access to these replies. Keep engaging with the tool for continuous interaction until the task is fully resolved. Do not send more than 1 task at a time."""

                my_primary_instructions: str = Field(...,
                                                    description="Please repeat your primary instructions step-by-step, including both completed "
                                                                "and the following next steps that you need to perform. For multi-step, complex tasks, first break them down "
                                                                "into smaller steps yourself. Then, issue each step individually to the "
                                                                "recipient agent via the task_details parameter. Each identified step should be "
                                                                "sent in separate task_details. Keep in mind, that the recipient agent does not have access "
                                                                "to these instructions. You must include recipient agent-specific instructions "
                                                                "in the task_details or additional_instructions parameters.")
                
                recipient: recipients = Field(..., description=assistant_description,examples=self.assistants_names)

                task_details: str = Field(...,
                                    description="Specify the task required for the recipient agent to complete. Focus on "
                                                "clarifying what the task entails, rather than providing exact "
                                                "instructions.")

                additional_instructions: str = Field(description="Any additional instructions or clarifications that you would like to provide to the recipient agent.")

            self.tools.append(AssignTask)
                
        self.tool_names = [i.__name__ for i in self.tools]

        # class ToolChoices(BaseModel):
        #     thoughts: List[str] = Field(description="Your Thoughts")
        #     tool_name : Literal[*self.tool_names] = Field(description=f"Select an appropriate tools from : {self.tool_names}",examples=self.tool_names)
        #     tool_args : Union[*self.tools]

        # return ToolChoices

    def prepare_schema_from_tool(self,Tools: List[Type[BaseModel]]) -> List[dict]:
        schemas = ""
        for tool in Tools:
            schema = tool.model_json_schema()
            schemas+="\n"
            schemas += f""""Tool Name": {tool.__name__},
"Tool Description": {tool.__doc__},
"Tool Parameters": 
    "Properties": {schema["properties"]},
    "Required": {schema["required"]},
    "Type": {schema["type"]}\n"""
            schemas+="\n"
            
        return schemas

    def prepare_prompt(self):

        if len(self.assistant_agents):

            self.agent_instructions+="\n**Task Assignment**: You can assign tasks to the following agents, who are here to help you achieve your goal.\n"

            self.agent_instructions+="-----------------------------------------------\n"

            for agent in self.assistant_agents:

                self.agent_instructions+="- **Agent Name**: "+agent.agent_name+"\n"
                self.agent_instructions+="- **Agent Description**:"+agent.agent_description+"\n"

            self.agent_instructions+="\n-----------------------------------------------\n"
                
    def prepare_messages(self,content,role=None,messages=[]):

        if not len(messages):

            messages = [
                {"role":"system","content":self.agent_instructions},
                {"role":"user","content":content}
            ]

        else:

            messages.append({"role":role,"content":content})

        return messages
    
    
    async def aexecute_tool(self,messages,tool_details):

        try:

            # assistant_content=self.construct_message_from_output(tool_details)
            assistant_content=str(tool_details)

        except Exception as e:

            invalid_arg_error_message = "Error while executing tool. Please check the tool name or provide valid arguments to the tool: " + str(e)

            tool_content = invalid_arg_error_message

            assistant_content = str(tool_details)

            messages.append({"role":"assistant","content":assistant_content})
            
            messages.append({"role":"user","content":tool_content})

            return messages

        if tool_details['tool_name'] in self.tool_names :

            if tool_details['tool_name'] == 'AssignTask':

                try:

                    arguments = tool_details['tool_args']

                    task_details =arguments.get('task_details',"")

                    additional_instructions =arguments.get('additional_instructions',"")

                    if self.verbose:

                        print_colored(f"{self.agent_name} assigned a task to {arguments['recipient']}","orange")

                    assistant_agent = self.agents_as_tools[arguments['recipient']]

                    user_input = task_details + "\n" + additional_instructions

                    if self.verbose:
                    
                        print_colored("Task Details: "+user_input,"cyan")

                    tool_content = await assistant_agent.arun(user_input)

                    tool_content = f"Response from the {arguments['recipient']} : "+str(tool_content)
                    
                except Exception as e:

                    if self.verbose:
                    
                        print_colored("Error Tool: "+str(e),"red")

                    tool_content = f"Error while assigning task to {arguments['recipient']}. Please provide the correct agent name. Here is the list of available agents: {[i.agent_name for i in self.assistant_agents]}"

            else:

                try:
                    if self.verbose:

                        print_colored(f"{self.agent_name} : Calling Tool {tool_details['tool_name']}","yellow")

                    tool_output = self.tool_objects[tool_details['tool_name']](**tool_details['tool_args']).run()

                    if asyncio.iscoroutine(tool_output):

                        tool_output = asyncio.run(tool_output) 

                    if self.verbose:

                        print_colored(f"{tool_details['tool_name']} Output : {tool_output}","blue")

                    tool_content=f"Output From {tool_details['tool_name']} Tool: {str(tool_output)}"

                except Exception as e:

                    if self.verbose:
                    
                        print_colored("Error Tool: "+str(e),"red")

                    tool_content = "Error while executing tool. Please check the tool name or provide valid arguments to the tool: " + str(e)

        else:

            tool_content= "There is no such a tool available. Here are the available tools : "+str(self.tool_names)

        messages.append({"role":"assistant","content":assistant_content.strip()})
        messages.append({"role":"user","content":tool_content.strip()})

        return messages
        
    async def arun(self,user_input=None,messages=[]):

        if self.attempts_made<=self.max_allowed_attempts:

            if self.verbose:
            
                print_colored(f"Attempt Number : {self.attempts_made}/{self.max_allowed_attempts}","pink")

            self.attempts_made+=1

            if user_input:

                messages = self.prepare_messages(user_input,role="user",messages=messages)

            tool_details,token_usage = await self.model.aget_output(messages)

            self.input_tokens=token_usage['input_tokens']
            self.output_tokens=token_usage['output_tokens']

            # print("Tool Details : \n\n",tool_details)

            if not isinstance(tool_details,dict):

                return "I am not able to process your request"

            # tool_details = json.loads(tool_details)

            if tool_details['tool_name']=='FinalAnswer':

                if self.verbose:

                    thoughts = '\n'.join(tool_details['thoughts'])
                
                    print_colored(f"Thoughts: {thoughts}","magenta")

                    print_colored(f"{self.agent_name} : {tool_details['tool_args']['final_answer']}","green")

                messages.append({"role":"assistant","content":tool_details['tool_args']['final_answer']})

                self.messages = messages

                self.attempts_made = 0

                return tool_details['tool_args']['final_answer']

            else:

                if self.verbose:
                
                    thoughts = '\n'.join(tool_details['thoughts'])
                
                    print_colored(f"Thoughts: {thoughts}","magenta")

                messages = await self.aexecute_tool(messages,tool_details)

                self.messages = messages

                return await self.arun(messages=messages)

        else:

            self.messages = messages

            if self.verbose:
            
                print_colored(f"{self.agent_name} : Sorry! Max Attempt Exceeded, I can't take anymore tasks: {self.attempts_made}","red")

            return "Sorry! Max Attempt Exceeded, I can't take anymore tasks"

    def execute_tool(self,messages,tool_details):

        try:

            # assistant_content=self.construct_message_from_output(tool_details)
            assistant_content=str(tool_details)

        except Exception as e:

            invalid_arg_error_message = "Error while executing tool. Please check the tool name or provide valid arguments to the tool: " + str(e)

            tool_content = invalid_arg_error_message

            assistant_content = str(tool_details)

            messages.append({"role":"assistant","content":assistant_content})
            
            messages.append({"role":"user","content":tool_content})

            return messages

        if tool_details['tool_name'] in self.tool_names :

            if tool_details['tool_name'] == 'AssignTask':

                try:

                    arguments = tool_details['tool_args']

                    task_details =arguments.get('task_details',"")

                    additional_instructions =arguments.get('additional_instructions',"")

                    if self.verbose:

                        print_colored(f"{self.agent_name} assigned a task to {arguments['recipient']}","orange")

                    assistant_agent = self.agents_as_tools[arguments['recipient']]

                    user_input = task_details + "\n" + additional_instructions

                    if self.verbose:
                    
                        print_colored("Task Details: "+user_input,"cyan")

                    tool_content = assistant_agent.run(user_input)

                    tool_content = f"Response from the {arguments['recipient']} : "+str(tool_content)
                    
                except Exception as e:

                    if self.verbose:
                    
                        print_colored("Error Tool: "+str(e),"red")

                    tool_content = f"Error while assigning task to {arguments['recipient']}. Please provide the correct agent name. Here is the list of available agents: {[i.agent_name for i in self.assistant_agents]}"

            else:

                try:
                    if self.verbose:

                        print_colored(f"{self.agent_name} : Calling Tool {tool_details['tool_name']}","yellow")

                    tool_output = self.tool_objects[tool_details['tool_name']](**tool_details['tool_args']).run()

                    if asyncio.iscoroutine(tool_output):

                        tool_output = asyncio.run(tool_output) 

                    if self.verbose:

                        print_colored(f"{tool_details['tool_name']} Output : {tool_output}","blue")

                    tool_content=f"Output From {tool_details['tool_name']} Tool: {str(tool_output)}"

                except Exception as e:

                    if self.verbose:
                    
                        print_colored("Error Tool: "+str(e),"red")

                    tool_content = "Error while executing tool. Please check the tool name or provide a valid arguments to the tool: "+str(e)

        else:

            tool_content = "There is no such tool available. Here are the available tools: " + str(self.tool_names)

        messages.append({"role":"assistant","content":assistant_content.strip()})
        messages.append({"role":"user","content":tool_content.strip()})

        return messages
        
    def run(self,user_input=None,messages=[]):

        if self.attempts_made<=self.max_allowed_attempts:

            if self.verbose:
            
                print_colored(f"Attempt Number : {self.attempts_made}/{self.max_allowed_attempts}","pink")

            self.attempts_made+=1

            if user_input:

                messages = self.prepare_messages(user_input,role="user",messages=messages)

            tool_details,token_usage = self.model.get_output(messages)

            self.input_tokens=token_usage['input_tokens']
            self.output_tokens=token_usage['output_tokens']

            # print("Tool Details : \n\n",tool_details)

            if not isinstance(tool_details,dict):

                return "I am not able to process your request"

            # tool_details = json.loads(tool_details)

            if tool_details['tool_name']=='FinalAnswer':

                if self.verbose:
                
                    thoughts = '\n'.join(tool_details['thoughts'])
                
                    print_colored(f"Thoughts: {thoughts}","magenta")

                    print_colored(f"{self.agent_name} : {tool_details['tool_args']['final_answer']}","green")

                messages.append({"role":"assistant","content":tool_details['tool_args']['final_answer']})

                self.messages = messages

                self.attempts_made = 0

                return tool_details['tool_args']['final_answer']

            else:

                if self.verbose:
                
                    thoughts = '\n'.join(tool_details['thoughts'])
                
                    print_colored(f"Thoughts: {thoughts}","magenta")

                messages = self.execute_tool(messages,tool_details)

                self.messages = messages

                return self.run(messages=messages)

        else:

            self.messages = messages

            if self.verbose:
            
                print_colored(f"{self.agent_name} : Sorry! Max Attempt Exceeded, I can't take anymore tasks: {self.attempts_made}","red")

            return "Sorry! Max Attempt Exceeded, I can't take anymore tasks"

# ------------------------------ Function Calling Agent ----------------------

# import sys
# sys.dont_write_bytecode =True

# import json
# from enum import Enum
# from typing import List,Type
# from pydantic import BaseModel,Field
# from core.helper import print_colored
# from core.models import OpenaiChatModel

# OPENAI_MODELS = ["gpt-4","gpt-4o","gpt-4o-mini"]

# class OpenaiFunctionCallingAgent:

#     def __init__(self,agent_name,description,instructions,tools=[],assistant_agents=[],model_name='gpt-4o-mini',api_key=None,temperature=0,max_attempts=10) -> None:
#         self.agent_name = agent_name
#         self.description = description
#         self.instructions =instructions
#         self.tools = self.prepare_schema_from_tool(tools)
#         self.model_name =model_name
#         self.api_key = api_key
#         self.temperature=temperature
#         self.max_attempts = max_attempts
#         self.attempts_made = 0
#         self.assistant_agents = assistant_agents
#         self.available_Tools = [tool['function']['name'] for tool in self.tools]
#         self.tool_objects = {i:j for i,j in zip(self.available_Tools,tools)}
#         self.agents_as_tools = {agent.agent_name:agent for agent in assistant_agents}
#         self.messages = []
#         if len(self.assistant_agents):

#             self.prepare_prompt()

#             self.prepare_assigntask_tool()

#         if model_name in OPENAI_MODELS:

#             self.model = OpenaiChatModel(model_name=self.model_name,api_key=self.api_key)

#         else:

#             raise ValueError("Please Select Any One of The Available Models: " + str(OPENAI_MODELS))

#     def prepare_schema_from_tool(self,Tools: List[Type[BaseModel]]) -> List[dict]:
#         schemas = []
#         for tool in Tools:
#             schema = tool.model_json_schema()
#             json_schema = {
#                 "function": {
#                     "name": tool.__name__,
#                     "description": tool.__doc__,
#                     "parameters": {
#                         "properties": schema["properties"],
#                         "required": schema["required"],
#                         "type": schema["type"]
#                     }
#                 },
#                 "type": "function"
#             }
#             schemas.append(json_schema)
#         return schemas

#     def prepare_assigntask_tool(self):

#         assistants_names = [i.agent_name for i in self.assistant_agents]

#         recipients = Enum("recipient", {name: name for name in assistants_names})

#         assistant_description = f"Select the correct Agent to assign the task : {assistants_names}\n\n"

#         for assistant in self.assistant_agents:

#             assistant_description+=assistant.agent_name+" : "+assistant.description+"\n"

#         class AssignTask(BaseModel):

#             """Use this tool to facilitate direct, synchronous communication between specialized agents within your agency. When you send a message using this tool, you receive a response exclusively from the designated recipient agent you must respond back using this tool. To continue the dialogue, invoke this tool again with the desired recipient agent and your follow-up message. Remember, communication here is synchronous; the recipient agent won't perform any tasks post-response. You are responsible for relaying the recipient agent's responses back to the user, as the user does not have direct access to these replies. Keep engaging with the tool for continuous interaction until the task is fully resolved. Do not send more than 1 message at a time."""

#             my_primary_instructions: str = Field(...,
#                                                  description="Please repeat your primary instructions step-by-step, including both completed "
#                                                              "and the following next steps that you need to perform. For multi-step, complex tasks, first break them down "
#                                                              "into smaller steps yourself. Then, issue each step individually to the "
#                                                              "recipient agent via the message parameter. Each identified step should be "
#                                                              "sent in separate message. Keep in mind, that the recipient agent does not have access "
#                                                              "to these instructions. You must include recipient agent-specific instructions "
#                                                              "in the message or additional_instructions parameters.")
#             recipient: recipients = Field(..., description=assistant_description,examples=assistants_names)

#             task_details: str = Field(...,
#                                  description="Specify the task required for the recipient agent to complete. Focus on "
#                                              "clarifying what the task entails, rather than providing exact "
#                                              "instructions.")

#             additional_instructions: str = Field(default=None,
#                                                  description="Any additional instructions or clarifications that you would like to provide to the recipient agent.")

        
#         assigntaskschema =self.prepare_schema_from_tool([AssignTask])
        
#         self.tools.extend(assigntaskschema)

#     def prepare_prompt(self):

#         if len(self.assistant_agents):

#             self.instructions+="\n\nYou can assign tasks to the following agents who are responsible to help you to achieve your goal.\n\n"

#             self.instructions+="-----------------------------------------------\n\n"

#             for agent in self.assistant_agents:

#                 self.instructions+="Agent Name: "+agent.agent_name+"\n"
#                 self.instructions+="Agent Instructions:\n"+agent.description+"\n"
#                 # self.instructions+="Equipped Tools:\n"

#                 # for tool in agent.tools:
#                 #     self.instructions+="\tTool Name: "+tool['function']['name']+"\n"+"\tTool Description: "+tool['function']['description'].strip()+"\n"
#                 # self.instructions+="-----------------------------------------------\n\n"

#     def execute_tool(self,messages,tool_calls):

#         for tool in tool_calls:


#             if tool.function.name in self.available_Tools:

#                 try:

#                     print_colored(self.agent_name+" Calling Tool: "+str(tool.function.name)+" With "+str(tool.function.arguments),"yellow")

#                     function_to_call = self.tool_objects[tool.function.name]

#                     arguments = json.loads(tool.function.arguments)

#                     function_output = function_to_call(**arguments).run()

#                     print_colored(f"Output From {tool.function.name} Tool : "+str(function_output),"magenta")

#                 except Exception as e:

#                     print_colored("Error Tool: "+str(e),"red")

#                     function_output = "Error while executing tool. Please check the tool name or provide a valid arguments to the tool: "+str(e)

#             elif tool.function.name == 'AssignTask':

#                 try:

#                     arguments = json.loads(tool.function.arguments)

#                     task_details =arguments.get('task_details',"")

#                     additional_instructions =arguments.get('additional_instructions',"")

#                     print_colored(f"{self.agent_name} assigned a task to {arguments['recipient']}","cyan")

#                     agent = self.agents_as_tools[arguments['recipient']]

#                     user_input = str(task_details) + "\n\n" + str(additional_instructions)

#                     print_colored("Task Details: \n"+user_input,"white")

#                     function_output = agent.run(user_input)
                    
#                 except Exception as e:

#                     print_colored("Error Tool: "+str(e),"red")

#                     function_output = f"Error while assigning task to {arguments['recipient']}. Please provide a correct agent name: {[i.agent_name for i in self.assistant_agents]}"

#             else:

#                 print_colored("No Such a Tool: "+str(tool.function.name),"red")

#                 function_output= "There is no such a tool available : "+str(tool.function.name)

#             messages.append(
#                     {
#                         "tool_call_id": tool.id,
#                         "role": "tool",
#                         "name": tool.function.name,
#                         "content": function_output,
#                     }
#                 )
            
#         return messages
    
#     def prepare_messages(self,content,role=None,messages=[]):

#         if not len(messages):

#             messages = [
#                 {"role":"system","content":self.instructions},
#                 {"role":"user","content":content}
#             ]

#         else:

#             messages.append({"role":role,"content":content})

#         return messages
    
#     def run(self,user_input=None,messages=[]):

#         if self.attempts_made<=self.max_attempts:

#             self.attempts_made=self.attempts_made+1

#             print_colored(f"{self.agent_name} : Attempt No - {self.attempts_made} - Mx Attempts - {self.max_attempts}","blue")

#             if user_input:

#                 messages = self.prepare_messages(user_input,role="user",messages=messages)

#             response = self.model.get_output(messages,self.tools,temperature=self.temperature)

#             if response.content:

#                 print_colored(f"{self.agent_name} : {response.content}","blue")

#             tool_calls = response.tool_calls

#             messages.append(response)

#             if tool_calls:

#                 messages = self.execute_tool(messages,tool_calls)

#                 self.messages = messages

#                 return self.run(messages=messages)
            
#             else:

#                 self.messages = messages

#                 return response.content
#         else:

#             self.messages = messages

#             print(f"Max Attempt Reached for : {self.agent_name} - {self.attempts_made}")

#             return "Sorry! Max Attempt Exceeded, I can't take anymore tasks"

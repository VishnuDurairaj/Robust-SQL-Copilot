import os
import uuid
import hashlib
import json
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv
from typing import Union, List

load_dotenv()

class AddTableContext:

    def __init__(self,model_name,api_key=None,max_tokens=4000,temperature=0.5,attempts=5):

        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

        if not self.api_key:

            raise ValueError("Please set your OPENAI_API_KEY.")

        self.model_name =model_name
        self.max_tokens =max_tokens
        self.temperature=temperature
        self.attempts =attempts
        
        self.openai_client = AsyncOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),  # This is the default and can be omitted
        )
    async def get_output(self,messages,response_format={"type": "json_object"}) -> None:

        if isinstance(response_format,dict):
            chat_completion = await self.openai_client.chat.completions.create(
                messages=messages,
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format=response_format

            )
        else:

            chat_completion = await self.openai_client.chat.completions.create(
                messages=messages,
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

        response_message = chat_completion.choices[0]

        return response_message

    async def filter_individual_table_columns(self,user_question,table_schema):

        system_prompt_filter = """You are an expert data analyst AI assistant specialized in identifying relevant columns from a single table to answer user questions effectively. The user will provide one table at a time, along with a natural language query. 
Your task is to analyze the query, interpret the table schema, and select only the columns required to answer the question. 
Note that while other tables might be necessary to fully answer the question, your goal is to determine how the given table alone contributes toward addressing the query. 
Provide a structured description of the table with the selected columns, explaining how these columns relate to the question."""

        user_prompt_filter =f"""I have a table and a question. Analyze the given table schema and identify only the columns that would contribute to answering the question. 
While other tables might be needed for a complete answer, focus on how this table alone can help. 
Provide a clear description of the table and the selected columns.

User Question : {user_question}

Table Schema : {table_schema['text_data']}

### The output should follow the below format:

If the table is useful to answer the user's question, include it in the response using the appropriate format.


    Database Name: Name of the database  
    Table Name: Name of the table  
    Table Description: Provide a concise description how the table.

    To answer user's question(do not mention the question), the following columns from the `table name` table are relevant:

    1. Column name1 : Column1 description
    2. Column name2 : Column2 description
    ...
    ...
    Similarly add all the relevant columns.

"Otherwise, if the table is not relevant to the user's question, return an empty string ""."

Only include information explicitly requested. Do not mention any other details.
"""
    
        messages = [{"role":"system","content":system_prompt_filter},
                    {"role":"user","content":user_prompt_filter}]
        
        final_response = ""

        for attempt in range(self.attempts):

            response = await  self.get_output(messages,response_format="string")

            if response.finish_reason!="stop":

                messages.append({"role":"assistant","content":response.message.content})
                conversation_history= "Please continue."
                messages.append({"role":"user","content":conversation_history})

            else:

                if not final_response:

                    final_response= response.message.content

                else:

                    final_response+= response.message.content


                table_schema.update({'filtered_columns':final_response})

                return table_schema

        table_schema.update({'filtered_columns':final_response})

        return table_schema

    async def filter_columns(self,user_question:str,all_tables:list,batch:int=10):

        sub_task = []

        final_output = []

        for table in all_tables:

            if len(sub_task)<=batch:

                sub_task.append(self.filter_individual_table_columns(user_question,table))

            else:

                results = await asyncio.gather(**sub_task)

                sub_task = []

                final_output.extend(results)

        if len(sub_task):

            results = await asyncio.gather(*sub_task)

            final_output.extend(results)

        return final_output

    async def add_individual_table_context(self,table_schema,all_tables=[]):

        print("Adding Context....")

        table_description_system_prompt = """You are an expert database and business developer specializing in documentation
Your task is to review database schemas and generate comprehensive documentation in JSON format. 
Focus on providing insights relevant to the betting industry, including table purposes, column descriptions, 
and potential use cases. Be concise yet informative, and ensure all output is in valid JSON format."""


        initial_user_prompt = f"""
Please generate comprehensive documentation for the following database schema in JSON format only. 
The documentation should include:
1. A brief overview of the table's purpose and its role
2. Detailed descriptions of each column, including its data type, purpose, and any relevant notes specific to the table
3. Any additional insights, best practices, or potential use cases for this table
4. Comments on the creation and last update times of the table, if relevant to its usage or data freshness.
5. Identify the relationships between tables through foreign keys as specified in the schema. Only include relationships that are explicitly stated in the schema; do not make any assumptions. If there are no relationship stated in the schema just leave it as empty list.

Here's the schema:\n\n
{table_schema}

Please provide the output in the following format:
```json
{{
    "DatabaseName": "Name of the database",
    "TableSchema": "Name of the table schema",
    "TableName": "Name of the table",
    "TableDescription": "Brief overview of the table",
    "Columns": [
    {{
        "name": "column_name",
        "type": "data_type",
        "description": "Detailed description and purpose of the column"
    }},
    // ... all other columns
    ],
    "AdditionalInsights": [
    "Insight 1",
    "Insight 2",
    // ... other insights
    ],
    "CommonQueries": [
    "List of business questions that can be answered using this table"
    ],
    "TableRelationship:[
    {{
    "ConnectedTableName": "Provide the name of the related table based on the foreign key connection.",
    "SharedColumn": "Specify the column that is common between the two tables (acting as the foreign key).",
    "ConnectionType": "Describe the type of relationship (e.g., one-to-many, many-to-many) based on the schema.",
    "Purpose": "Explain the purpose or intended use of this connection as suggested by the schema."
    }}
    ]
}}
```

If you need more space to complete the documentation, end your response with "[CONTINUE]" and I will prompt you to continue.
"""

        messages = [{"role":"system","content":table_description_system_prompt},
                    {"role":"user","content":initial_user_prompt}]
        
        final_response = ""
        
        for attempt in range(self.attempts):

            response = await self.get_output(messages)

            if response.finish_reason!="stop":

                messages.append({"role":"assistant","content":response.message.content})
                conversation_history= "Please continue the JSON documentation where you left off. Remember it should be a valid JSON and do not begin from begining just continue from where you left off and try to complete the JSON documentation."
                messages.append({"role":"user","content":conversation_history})

            else:

                if not final_response:

                    final_response= response.message.content

                else:

                    final_response+= response.message.content

                try:
                
                    return json.loads(final_response)
                
                except Exception as e:

                    messages.append({"role":"assistant","content":final_response})
                    messages.append({"role":"user","content":f"I am facing the following error while loading it as JSON. Please fix the issue and provide a valid JSON : {e}"})
        
        return final_response

    async def process_all_schema(self,filtred_data,common_cols,batch=5):

        tables = [i[1].reset_index(drop=True).to_markdown() for i in filtred_data.groupby(['table_catalog','table_schema','table_name'])]

        sub_task = []

        final_output = []

        for task in range(len(tables)):

            if len(sub_task)<=batch:

                sub_task.append(self.add_individual_table_context(tables[task]))

            else:

                results = await asyncio.gather(*sub_task)

                sub_task = []

                final_output.extend(results)

        if len(sub_task):

            results = await asyncio.gather(*sub_task)

            final_output.extend(results)

        data_points = self.__prepare_text(final_output,common_cols)

        return data_points

    def __prepare_text(self,output,common_cols):

        data_points = {}

        for sample in output:

            ids = self._deterministic_uuid(sample['DatabaseName']+sample['TableName'])

            data_points[sample['TableName']] = {"chunks":[],"text_data":"","ids":[],"relationships":[],"common_columns":""}

            base_str = f"""
Database Name: {sample['DatabaseName']}
Table Name: {sample['TableName']}
Table Description: {sample['TableDescription']}
Columns: The following columns are avilable in this table.
"""
            data_points[sample['TableName']]['chunks'].append(base_str.strip())

            data_points[sample['TableName']]['ids'].append(ids)

            col_str = ""

            columns = sample.get('Columns',"")

            for col in columns:

                col_str+="\tname : "+col['name'] + "\n"
                col_str+="\ttype : "+col['type'] +"\n"
                col_str+="\tdescription : "+col['description'] +"\n\n"

                col_des = f"""column name : {col['name']}
                    column type : {col['type']}
                    description : {col['description']}"""

                data_points[sample['TableName']]['chunks'].append(col_des.strip())

                data_points[sample['TableName']]['ids'].append(ids)

            table_relationship = "The following outlines the relationships between this table and other tables:\n"

            table_rel = sample.get('TableRelationship',"")

            data_points[sample['TableName']]['relationships'] = table_rel

            for rels in common_cols:

                if (rels['database']== sample['DatabaseName'] or rels['table_schema']== sample['TableSchema']) and rels['table_name'] == sample['TableName']:

                    data_points[sample['TableName']]['common_columns']= rels['relation']

            for rel in table_rel:

                table_relationship+="Connected Table Name :"+rel['ConnectedTableName']+"\n"
                table_relationship+="Shared Column Name:"+rel['SharedColumn']+"\n"
                table_relationship+="Purpose :"+rel['Purpose']+"\n\n"

            final_doc_str = base_str + col_str + table_relationship

            data_points[sample['TableName']]['text_data'] = final_doc_str

        return data_points
    
    def _deterministic_uuid(self,content: Union[str, bytes]) -> str:
        """Creates deterministic UUID on hash value of string or byte content.
        Args:
            content: String or byte representation of data.
        Returns:
            UUID of the content.
        """
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        elif isinstance(content, bytes):
            content_bytes = content
        else:
            raise ValueError(f"Content type {type(content)} not supported !")

        hash_object = hashlib.sha256(content_bytes)
        hash_hex = hash_object.hexdigest()
        namespace = uuid.UUID("00000000-0000-0000-0000-000000000000")
        content_uuid = str(uuid.uuid5(namespace, hash_hex))
        return content_uuid
    
    
# model = AddTableContext("gpt-4o-mini",max_tokens=4000)
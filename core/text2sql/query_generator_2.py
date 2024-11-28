import sys
sys.dont_write_bytecode =True

import os
import logging
import asyncio
import instructor
import nest_asyncio
import pandas as pd
from typing import List
from openai import OpenAI
from pydantic import BaseModel,Field
from difflib import get_close_matches
from openai import OpenAI as instructor_OpenAI
from core.text2sql.sql_connectors import SQLConnector
from core.text2sql.vectorestores import QdrantVectorStore
from core.text2sql.add_context import AddTableContext
from core.text2sql.text_splitter import Schema2Chunks

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

nest_asyncio.apply()

class SQLqueryFormat(BaseModel):
    requirements: str = Field(description="Describe the user requirements in details")
    step_by_step_plan: str = Field(description="Write step by step plan with the relevant tables to generate accurate SQL query to provide all the information listed in the checklist or fix the error in the sql query")
    query_type: str = Field(description="The type of the sql query it could be either intermediate_query, final_query or explanation",examples=["intermediate_query","final_query","explanation"])
    list_of_intermediate_query: List[str] = Field(description="One or more intermediate queries",examples=["SELECT DISTINCT category FROM table_schema.table_name;"])
    final_query: str = Field(description="The accurate query to answer user question or empty in case of irrelevant question",examples=["Select * from table_schema.table_name;",""])
    explanation:str = Field(description="If the provided schema are not sufficient to answer user question")

class SQLColumnValue(BaseModel):
    column : str = Field(description="The column name from the SQL query")
    value : List[str] = Field(description="The values from the user question which should be used in where clause")

class ColumnAndValue(BaseModel):
    column_and_values : List[SQLColumnValue] = Field(description="The columns and the values associated with them. Ignore Date related columns and values, foucs only on categorical columns.")

example_syntax = {
    "MySQL": "SELECT column_name FROM database_name.table_name WHERE condition;\n",
    "PostgreSQL": 'SELECT column_name FROM "schema_name"."table_name" WHERE condition;\nSELECT DISTINCT column_name FROM "schema_name"."table_name";\n. Never use this syntax :"schema_name.table_name" ',
    "Snowflake": 'SELECT column_name FROM schema_name.table_name WHERE condition;\n',
    "SQL Server": 'SELECT column_name FROM schema_name.table_name WHERE condition;\n'
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler()]
)

class Text2SQL(QdrantVectorStore, SQLConnector,AddTableContext,Schema2Chunks):

    def __init__(self,model_name,api_key,db_type,host,port,username,password,database,db_location=None, db_url="http://qdrant:6333",dense_model="sentence-transformers/all-MiniLM-L6-v2", sparse_model="prithivida/Splade_PP_en_v1", hybrid=True,override_existing_index=False,max_attempts=5,add_additional_context=True) -> None:
        
        self.api_key = os.getenv("OPENAI_API_KEY") or api_key

        if not self.api_key:

            raise ValueError("Please Set Your OPENAI_API_KEY.")

        # Initialize QdrantVectorStore

        self.collection_name = f"{self._deterministic_uuid(content=f"{host,port,username,password,database}")}_collection"

        if not db_url:

            db_location = self._deterministic_uuid(content=f"{host,port,username,password,database}")

            QdrantVectorStore.__init__(self,db_location=db_location,collection_name=self.collection_name, dense_model=dense_model, sparse_model=sparse_model, hybird=hybrid)
        
        else:

            QdrantVectorStore.__init__(self, url=db_url,collection_name=self.collection_name, dense_model=dense_model, sparse_model=sparse_model, hybird=hybrid)
        
        # Initialize SQLConnector
        SQLConnector.__init__(self,db_type,host,port,username,password,database)

        AddTableContext.__init__(self,model_name)

        Schema2Chunks.__init__(self,model_name)

        self.model_name = model_name

        self.max_attempts = max_attempts

        self.override_existing_index=override_existing_index

        self.add_additional_context = add_additional_context

        self.instructor_client = instructor.from_openai(instructor_OpenAI(api_key=self.api_key))

        self.db_type,self.host,self.port,self.username,self.password,self.database = db_type,host,port,username,password,database

        self.__connect_to_db()

    def __connect_to_db(self):
        # Use getattr to dynamically call the correct method

        logging.info(f"Connecting to The Database.....!")

        func_name = f"connect_to_{self.db_type}"

        func = getattr(self, func_name)

        func(self.host, self.port, self.username, self.password, self.database)

        if not self.client_qdrant.collection_exists(self.collection_name) or self.client_qdrant.count(self.collection_name).count==0 or self.override_existing_index:

            filtred_data = self.schema_description

            common_cols = self.extract_table_relationships(filtred_data)

            if self.add_additional_context:

                documents = []

                ids = []

                metadata = []

                data_points = asyncio.run(self.process_all_schema(filtred_data,common_cols))

                for key in data_points.keys():

                    documents.extend(data_points[key]['chunks'])
                    
                    metadata.extend([{"table_id":data_points[key]['ids'][0],"text_data":data_points[key]['text_data'],"relationships":data_points[key]['relationships'],"common_columns":data_points[key]['common_columns']}]*len(data_points[key]['chunks']))

                logging.info(f"Adding Schema details to VectorDB.....!")

            else:

                ids = []

                schemas =self.schema_data_to_train.to_dict(orient="records")

                documents,metadata =self.split_text(schemas,common_cols)

                logging.info(f"Adding Schema details to VectorDB.....!")

            return self.add_documents_to_schema_details(documents,ids,metadata)

    def TextAgent(self,messages,format):
        format = self.instructor_client.chat.completions.create(
            model=self.model_name,
            response_model=format,
            messages=messages,
            temperature=0,
            max_retries=self.max_attempts
        )
        return format.model_dump()

    def execute_inertmediate_query(self,user_question,sub_query):

        intermediate_results = "Below are the outputs of intermediate queries.\n\n"
        
        try:

            df = self.run_sql_query(sub_query)

            if df.shape[0]>=50:

                try:

                    messages=[
                    {"role":"system","content":"You are an helful assistant"},
                    {"role": "user", "content": self.prepare_user_prompt_to_get_column_and_value(user_question,sub_query)}
                    ]

                    col_val = self.TextAgent(messages,ColumnAndValue)
                    
                    df = self.reorder_dataframe(df,col_val)
                    
                except Exception as e:
                    logger.error(f"Error Occured while sorting the df: {str(e)}")

            intermediate_results+="Intermediate Query : "+sub_query + "\n"

            intermediate_results+="Output :\n"+df.iloc[:50,:].to_markdown()

            intermediate_results+="\n\n******************************************\n\n"

        except Exception as e:
            intermediate_results = f"I am getting the following error while executing the given SQL queries: {e} Please give me the correct query."
        return intermediate_results

    def prepare_user_prompt_to_get_column_and_value(self,query,sql_query):

        user_prompt_col_val = """You are given with user question and an intermediate sql query. you have to extract the column name from the SQL query and value from the user question which is associated with the given SQL query."""

        user_prompt_col_val+=f"\n\nUser Question: {query}"

        user_prompt_col_val+=f"\n\nIntermediate Query: {sql_query}"

        return user_prompt_col_val

    def reorder_dataframe(self,df, column_and_values):

        print("************************ Re-ordering ***********************************")
        
        final_df = []
        
        for i in column_and_values['column_and_values']:
            
            column = i['column']
            
            if column in df.columns:
                
                closest_matchs = []
                
                for value in i['value']:

                    standardized_value = value.replace("_", " ").title()
                    
                    closest_match = get_close_matches(standardized_value, df[column], n=1, cutoff=0.6)
                    
                    if len(closest_match):
                        
                        closest_matchs.append(closest_match[0])
                
                if len(closest_matchs):
                    
                    filtred_df = df[df[column].isin(closest_matchs)].iloc[:5,:]
                    
                    final_df.append(filtred_df)
        if len(final_df):
            reordered_df = pd.concat(final_df+[df]).reset_index(drop=True)
            return reordered_df.iloc[:len(df),:]
        return df


    def get_sql_query_type(self,query):
        """
        Determines the type of a SQL query.
        
        Parameters:
        query (str): The SQL query to analyze.
        
        Returns:
        str: The type of the SQL query (SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, or UNKNOWN).
        """
        query = query.strip().lower()
        
        if query.startswith("select") or query.startswith("with") or query.startswith("(select"):
            return "SELECT"
        elif query.startswith("insert"):
            return "INSERT"
        elif query.startswith("update"):
            return "UPDATE"
        elif query.startswith("delete"):
            return "DELETE"
        elif query.startswith("create"):
            return "CREATE"
        elif query.startswith("drop"):
            return "DROP"
        else:
            return "UNKNOWN"
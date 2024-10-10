import sys
sys.dont_write_bytecode =True

import pyodbc
import uuid
import pymysql
import psycopg2
import logging
import hashlib
import pandas as pd
from typing import Union
import snowflake.connector
from urllib.parse import quote_plus

ignore_default_schemas = [
    "mysql", "information_schema", "performance_schema", "sys",   # MySQL
    "INFORMATION_SCHEMA", "SNOWFLAKE", "SNOWFLAKE_SAMPLE_DATA",   # Snowflake
    "SNOWFLAKE_ACCOUNT_USAGE", "SNOWFLAKE_ORG_ADMIN",
    "SNOWFLAKE_SHARE", "SNOWFLAKE_LOAD_HISTORY",
    "INFORMATION_SCHEMA.TABLES", "INFORMATION_SCHEMA.COLUMNS",   # BigQuery
    "INFORMATION_SCHEMA.SCHEMATA", "INFORMATION_SCHEMA.ROUTINES",
    "INFORMATION_SCHEMA.VIEWS",
    "pg_catalog", "pg_toast", "pg_temp_1", "pg_toast_temp_1",     # PostgreSQL
    "sys", "guest", "db_owner", "db_accessadmin",                 # SQL Server
    "db_securityadmin", "db_ddladmin", "db_backupoperator",
    "db_datareader", "db_datawriter", "db_denydatareader",
    "db_denydatawriter",
    "SYS", "SYSTEM", "DBSNMP", "SYSMAN", "OUTLN",                 # Oracle
    "AUDSYS", "APPQOSSYS", "OJVMSYS", "DVF", "DVSYS",
    "LBACSYS", "GGSYS", "XS$NULL", "GSMADMIN_INTERNAL",
    "GSMCATUSER", "GSMUSER",
    "pg_catalog",                                        # Amazon Redshift
    "sqlite_master", "sqlite_temp_master", "sqlite_sequence",      # SQLite
    "sqlite_stat1", "sqlite_stat4",
    "SYSIBM", "SYSCAT", "SYSSTAT", "SYSTOOLS",                    # IBM Db2
    "SYSIBMADM", "SYSFUN", "SYSIBMTS",
    "mysql", "performance_schema",                                # MariaDB
    "information_schema",
    "information_schema", "pg_catalog", "crdb_internal"           # CockroachDB
]



ignore_default_schemas = [i.lower() for i in ignore_default_schemas]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SQLConnector:

    def __init__(self) -> None:
        self.schema_description = None
        self.dialect=None
        self.database_name = None

    def connect_to_mysql(self, host, port, username, password, database=None):
        # password = quote_plus(password)
        try:
            self.connection = pymysql.connect(
                host=host,
                user=username,
                password=password,
                database=database,
                port=port
            )
            self.dialect = "MySQL"
            self.database_name = database
            logger.info("Connection to the MySQL database established successfully.")
        except pymysql.MySQLError as e:
            logger.error(f"Error connecting to MySQL: {e}")
            self.connection = None

        query = """
        SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, COLUMN_DEFAULT, COLUMN_KEY, COLUMN_COMMENT 
        FROM INFORMATION_SCHEMA.COLUMNS;
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                data = cursor.fetchall()
                columns = [i[0] for i in cursor.description]
                df = pd.DataFrame(data, columns=columns)
                self.schema_description = self._prepare_schema_description(df)
                logger.info("Schema details fetched successfully.")
        except Exception as e:
            logger.error(f"Error fetching schema details: {e}")
            return None

    def connect_to_postgresql(self, host, port, username, password, database):
        # password = quote_plus(password)
        try:
            self.connection = psycopg2.connect(
                host=host,
                user=username,
                password=password,
                dbname=database,
                port=port
            )
            self.dialect = "PostgreSQL"
            self.database_name = database
            logger.info("Connection to the PostgreSQL database established successfully.")
        except psycopg2.Error as e:
            logger.error(f"Error connecting to PostgreSQL: {e}")
            self.connection = None
            self.database_name = database

        query = """
        SELECT 
            cols.table_catalog, 
            cols.table_schema, 
            cols.table_name, 
            cols.column_name, 
            cols.ordinal_position, 
            cols.column_default, 
            cols.is_nullable, 
            cols.data_type, 
            cols.character_maximum_length, 
            cols.numeric_precision, 
            cols.numeric_scale, 
            cols.datetime_precision,
            pgd.description AS column_comment
        FROM 
            information_schema.columns cols
        LEFT JOIN 
            pg_catalog.pg_statio_all_tables AS st
            ON cols.table_schema = st.schemaname AND cols.table_name = st.relname
        LEFT JOIN 
            pg_catalog.pg_description pgd
            ON pgd.objoid = st.relid AND pgd.objsubid = cols.ordinal_position
        WHERE 
            cols.table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY 
            cols.table_schema, 
            cols.table_name, 
            cols.ordinal_position;
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                data = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                df = pd.DataFrame(data, columns=columns)
                self.schema_description = self._prepare_schema_description(df)
                self.df= df
                logger.info("Schema details fetched successfully.")
        except Exception as e:
            logger.error(f"Error fetching schema details: {e}")
            return None

    def connect_to_sql_server(self, host, port, username, password, database):
        # password = quote_plus(password)
        try:
            connection_string = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host},{port};DATABASE={database};UID={username};PWD={password}'
            self.connection = pyodbc.connect(connection_string)
            self.dialect = "SQL Server"
            logger.info("Connection to the SQL Server database established successfully.")
        except pyodbc.Error as e:
            logger.error(f"Error connecting to SQL Server: {e}")
            self.connection = None
            self.database_name = database
            

        query = """
        SELECT 
            TABLE_CATALOG, 
            TABLE_SCHEMA, 
            TABLE_NAME, 
            COLUMN_NAME, 
            DATA_TYPE, 
            COLUMN_DEFAULT, 
            IS_NULLABLE, 
            COLUMNPROPERTY(object_id(TABLE_NAME), COLUMN_NAME, 'IsIdentity') AS IS_IDENTITY,
            (SELECT value FROM sys.extended_properties 
             WHERE major_id = object_id(TABLE_NAME) AND minor_id = COLUMNPROPERTY(object_id(TABLE_NAME), COLUMN_NAME, 'ColumnId')) AS COLUMN_COMMENT
        FROM 
            INFORMATION_SCHEMA.COLUMNS
        ORDER BY 
            TABLE_SCHEMA, 
            TABLE_NAME, 
            ORDINAL_POSITION;
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                data = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                df = pd.DataFrame(data, columns=columns)
                self.schema_description = self._prepare_schema_description(df)
                logger.info("Schema details fetched successfully.")
        except Exception as e:
            logger.error(f"Error fetching schema details: {e}")
            return None

    def connect_to_snowflake(self, account, user, password, warehouse, database, schema):
        # password = quote_plus(password)
        try:
            self.connection = snowflake.connector.connect(
                account=account,
                user=user,
                password=password,
                warehouse=warehouse,
                database=database,
                schema=schema
            )
            self.dialect = "Snowflake"
            self.database_name = database
            logger.info("Connection to the Snowflake database established successfully.")
        except snowflake.connector.Error as e:
            logger.error(f"Error connecting to Snowflake: {e}")
            self.connection = None

        query = """
        SELECT 
            table_catalog, 
            table_schema, 
            table_name, 
            column_name, 
            data_type, 
            column_default, 
            is_nullable, 
            comment as column_comment
        FROM 
            information_schema.columns
        WHERE 
            table_schema = %s;
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (schema,))
                data = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                df = pd.DataFrame(data, columns=columns)
                self.schema_description = self._prepare_schema_description(df)
                logger.info("Schema details fetched successfully.")
        except Exception as e:
            logger.error(f"Error fetching schema details: {e}")
            return None

    def _prepare_schema_description(self,data):
        try:

            data.columns = [i.lower() for i in data.columns]
            database_column = data.columns[data.columns.str.lower().str.contains("database")|data.columns.str.lower().str.contains("table_catalog")].to_list()[0]
            schema_column = data.columns[data.columns.str.lower().str.contains("table_schema")].to_list()[0]
            table_column = data.columns[data.columns.str.lower().str.contains("table_name")].to_list()[0]
            data_points = []
            ids = []
            category = []
            table_description = []
            # ignore_default_schemas = ["mysql","information_schema","performance_schema","sys"]
            filtred_data = data[~data[schema_column].isin(ignore_default_schemas)]
            # filtred_data.to_csv("a.csv",index=False)
            logging.info(f"Available Features: {len(filtred_data)}")
            if self.database_name:
                filtred_data_filtred = filtred_data[(filtred_data[schema_column]==self.database_name)|(filtred_data[database_column]==self.database_name)]
                logging.info(f"Features from the particular database: {len(filtred_data_filtred)}")
            if filtred_data_filtred.shape[0]>1:
                filtred_data = filtred_data_filtred.copy()
            for table in filtred_data[table_column].unique().tolist():
                db_name = set(filtred_data[filtred_data[table_column]==table][database_column].to_list()).pop()
                schema_name = set(filtred_data[filtred_data[table_column]==table][schema_column].to_list()).pop()
                doc = f"The following columns are in the {table} table in the {schema_name} database:\n\n"
                doc_str = ""
                for ind, row in filtred_data[filtred_data[table_column]==table][['column_name','column_comment']].iterrows():
                    if row['column_comment']:
                        doc_str+=row['column_name']+" - "+row['column_comment']+" "
                    else:
                        doc_str+=row['column_name']+", "

                table_description.append(doc+doc_str[:-2])
                # appending schema details
                doc+=filtred_data[filtred_data[table_column]==table].to_markdown()
                data_points.append(doc)
                ids.append(self._deterministic_uuid(doc))
                category.append("Schema Data")
            schema_dict = {"id":ids,"data_points":data_points,"table_description":table_description,"category":category}
            schema_data_to_train = pd.DataFrame(schema_dict)
            return schema_data_to_train
        except Exception as e:
            logger.error(f"Error fetching schema details: {e}")
            return None

    def disconnect(self):
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed.")

    # def run_sql_query(self, query):
    #     if not self.connection:
    #         logger.warning("Database connection is not established.")
    #         return None

    #     with self.connection.cursor() as cursor:
    #         cursor.execute(query)
    #         data = cursor.fetchall()
    #         column = [i[0] for i in cursor.description]
    #         df = pd.DataFrame(data, columns=column)
    #         logger.info("SQL query executed successfully.")
    #         return df

    def run_sql_query(self, query):
        if not self.connection:
            logger.warning("Database connection is not established.")
            return None

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                data = cursor.fetchall()
                column = [i[0] for i in cursor.description]
                df = pd.DataFrame(data, columns=column)
                return df

        except psycopg2.DatabaseError as e:
            logger.error(f"Database error occurred: {e} Retrying..")
            self.connection.rollback()
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                data = cursor.fetchall()
                column = [i[0] for i in cursor.description]
                df = pd.DataFrame(data, columns=column)
                logger.info("SQL query executed successfully.")
                return df


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
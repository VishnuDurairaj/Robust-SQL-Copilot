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
from collections import defaultdict

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

ignore_default_tables = ['data_dictionary','table_info','factspan_work_config_table']

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SQLConnector:

    def __init__(self,db_type,host,port,username,password,database) -> None:
        self.schema_description = None
        self.dialect=None
        self.database_name = None
        self.db_type,self.host,self.port,self.username,self.password,self.database = db_type,host,port,username,password,database

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
        SELECT 
            c.table_catalog AS table_catalog,
            c.table_schema AS table_schema,
            c.table_name AS table_name,
            c.column_name AS column_name,
            c.column_default AS column_default,
            c.data_type AS data_type,
            c.column_comment AS column_comment,
            CASE 
                WHEN kcu.constraint_name = 'PRIMARY' THEN 'YES'
                ELSE 'NO'
            END AS is_primary_key,
            kcu2.referenced_table_name AS referenced_table,
            kcu2.referenced_column_name AS referenced_column
        FROM 
            information_schema.columns c
        LEFT JOIN 
            information_schema.key_column_usage kcu 
            ON c.table_schema = kcu.table_schema
            AND c.table_name = kcu.table_name 
            AND c.column_name = kcu.column_name
            AND kcu.constraint_name = 'PRIMARY'
        LEFT JOIN 
            information_schema.key_column_usage kcu2
            ON c.table_schema = kcu2.table_schema
            AND c.table_name = kcu2.table_name
            AND c.column_name = kcu2.column_name
            AND kcu2.referenced_table_name IS NOT NULL
        WHERE 
            c.table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
        ORDER BY 
            c.table_schema,
            c.table_name,
            c.ordinal_position;
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
            cols.column_default, 
            cols.data_type, 
            pgd.description AS column_comment,
            CASE 
                WHEN tc.constraint_type = 'PRIMARY KEY' THEN 'YES' 
                ELSE 'NO' 
            END AS is_primary_key,
            fk_info.foreign_table_name AS referenced_table,
            fk_info.foreign_column_name AS referenced_column
        FROM 
            information_schema.columns cols
        LEFT JOIN 
            pg_catalog.pg_statio_all_tables AS st
            ON cols.table_schema = st.schemaname 
            AND cols.table_name = st.relname
        LEFT JOIN 
            pg_catalog.pg_description pgd
            ON pgd.objoid = st.relid 
            AND pgd.objsubid = cols.ordinal_position
        LEFT JOIN 
            information_schema.key_column_usage kcu
            ON cols.table_schema = kcu.table_schema
            AND cols.table_name = kcu.table_name
            AND cols.column_name = kcu.column_name
        LEFT JOIN 
            information_schema.table_constraints tc 
            ON kcu.constraint_name = tc.constraint_name
            AND tc.constraint_type = 'PRIMARY KEY'
        LEFT JOIN (
            SELECT 
                tc.table_schema, 
                tc.table_name, 
                kcu.column_name, 
                ccu.table_name AS foreign_table_name, 
                ccu.column_name AS foreign_column_name
            FROM 
                information_schema.table_constraints AS tc
            JOIN 
                information_schema.key_column_usage AS kcu 
                ON tc.constraint_name = kcu.constraint_name
            JOIN 
                information_schema.constraint_column_usage AS ccu 
                ON ccu.constraint_name = tc.constraint_name
            WHERE 
                tc.constraint_type = 'FOREIGN KEY'
        ) AS fk_info
        ON 
            cols.table_schema = fk_info.table_schema 
            AND cols.table_name = fk_info.table_name 
            AND cols.column_name = fk_info.column_name
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
        DECLARE @sql NVARCHAR(MAX);
        SET @sql = '
        SELECT 
            DB_NAME() AS table_catalog,
            s.name AS table_schema,
            t.name AS table_name,
            c.name AS column_name,
            OBJECT_DEFINITION(c.default_object_id) AS column_default,
            tp.name AS data_type,
            ep.value AS column_comment,
            CASE 
                WHEN pk.object_id IS NOT NULL THEN ''YES''
                ELSE ''NO''
            END AS is_primary_key,
            OBJECT_NAME(fk.referenced_object_id) AS referenced_table,
            COL_NAME(fk.referenced_object_id, fkc.referenced_column_id) AS referenced_column
        FROM 
            sys.tables t
        INNER JOIN 
            sys.schemas s ON t.schema_id = s.schema_id
        INNER JOIN 
            sys.columns c ON t.object_id = c.object_id
        INNER JOIN 
            sys.types tp ON c.user_type_id = tp.user_type_id
        LEFT JOIN 
            sys.extended_properties ep ON ep.major_id = c.object_id 
            AND ep.minor_id = c.column_id 
            AND ep.name = ''MS_Description''
        LEFT JOIN 
            sys.index_columns ic ON ic.object_id = t.object_id 
            AND ic.column_id = c.column_id
        LEFT JOIN 
            sys.indexes pk ON pk.object_id = t.object_id 
            AND pk.is_primary_key = 1 
            AND ic.index_id = pk.index_id
        LEFT JOIN 
            sys.foreign_key_columns fkc ON fkc.parent_object_id = t.object_id 
            AND fkc.parent_column_id = c.column_id
        LEFT JOIN 
            sys.foreign_keys fk ON fk.object_id = fkc.constraint_object_id
        WHERE 
            t.is_ms_shipped = 0
        ORDER BY 
            s.name, 
            t.name, 
            c.column_id;';

        -- Create a temporary table to hold results
        CREATE TABLE #TableRelationships (
            table_catalog NVARCHAR(128),
            table_schema NVARCHAR(128),
            table_name NVARCHAR(128),
            column_name NVARCHAR(128),
            column_default NVARCHAR(MAX),
            data_type NVARCHAR(128),
            column_comment SQL_VARIANT,
            is_primary_key NVARCHAR(3),
            referenced_table NVARCHAR(128),
            referenced_column NVARCHAR(128)
        );

        -- Cursor to execute across all databases
        DECLARE @dbname NVARCHAR(128);
        DECLARE db_cursor CURSOR FOR 
        SELECT name 
        FROM sys.databases 
        WHERE database_id > 4  -- Exclude system databases
            AND state = 0     -- Only online databases
            AND is_read_only = 0;  -- Exclude read-only databases

        OPEN db_cursor;
        FETCH NEXT FROM db_cursor INTO @dbname;

        WHILE @@FETCH_STATUS = 0
        BEGIN
            DECLARE @execsql NVARCHAR(MAX);
            SET @execsql = 'USE [' + @dbname + ']; INSERT INTO #TableRelationships ' + @sql;
            
            BEGIN TRY
                EXEC sp_executesql @execsql;
            END TRY
            BEGIN CATCH
                PRINT 'Error processing database: ' + @dbname;
            END CATCH
            
            FETCH NEXT FROM db_cursor INTO @dbname;
        END

        CLOSE db_cursor;
        DEALLOCATE db_cursor;

        -- Return the final results
        SELECT * FROM #TableRelationships
        ORDER BY 
            table_catalog,
            table_schema,
            table_name,
            column_name;

        -- Clean up
        DROP TABLE #TableRelationships;
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
            db_names = []
            table_schemas = []
            table_name = []
            # ignore_default_schemas = ["mysql","information_schema","performance_schema","sys"]
            filtred_data = data[~data[schema_column].isin(ignore_default_schemas)]
            filtred_data = filtred_data[~filtred_data[table_column].isin(ignore_default_tables)]
            self.df = filtred_data
            # filtred_data.to_csv("a.csv",index=False)
            logging.info(f"Available Features: {len(filtred_data)}")
            if self.database_name:
                filtred_data_filtred = filtred_data[(filtred_data[schema_column]==self.database_name)|(filtred_data[database_column]==self.database_name)]
                logging.info(f"Features from the particular database: {len(filtred_data_filtred)}")
            if filtred_data_filtred.shape[0]>1:
                filtred_data = filtred_data_filtred.copy()

            self.df = filtred_data
            
            for table in filtred_data[table_column].unique().tolist():
                db_name = set(filtred_data[filtred_data[table_column]==table][database_column].to_list()).pop()
                schema_name = set(filtred_data[filtred_data[table_column]==table][schema_column].to_list()).pop()
                doc = f"The following columns are in the {table} table in the {db_name} database under {schema_name} schema:\n\n"
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
                db_names.append(db_name)
                table_schemas.append(schema_name)
                table_name.append(table)
                category.append("Schema Data")
            schema_dict = {"database":db_names,"schema_name":table_schemas,"table_name":table_name,"id":ids,"data_points":data_points,"table_description":table_description,"category":category}
            self.schema_data_to_train = pd.DataFrame(schema_dict)
            return filtred_data
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

            logger.warning("Database connection is not established. Trying to connect")

            func_name = f"connect_to_{self.db_type.lower()}"
    
            func = getattr(self, func_name)

            self.connection = func(self.host,self.port,self.username,self.password,self.database)

            with self.connection.cursor() as cursor:
                cursor.execute(query)
                data = cursor.fetchall()
                column = [i[0] for i in cursor.description]
                df = pd.DataFrame(data, columns=column)
                return df

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
    
    def extract_table_relationships(self,df):
        """
        Extract table relationships from a DataFrame containing database schema information.
        Identifies relationships through both:
        1. Explicit foreign key references
        2. Matching column names between tables
        
        Args:
            df (pandas.DataFrame): DataFrame containing database schema information
        
        Returns:
            list: List of dictionaries containing table relationships
        """
        # Initialize results dictionary
        relationships = defaultdict(lambda: {
            'database': '',
            'table_schema':'',
            'table_name': '',
            'related_tables': defaultdict(lambda: {
                'explicit_refs': [],    # Relationships from foreign key references
                'possible_refs': []     # Relationships from matching column names
            })
        })
        
        # Create a mapping of table to its columns for faster lookup
        table_columns = defaultdict(list)
        for _, row in df.iterrows():
            table_name = row['table_name']
            column_name = row['column_name']
            table_columns[table_name].append({
                'column_name': column_name,
                'data_type': row['data_type'],
                'is_primary_key': row['is_primary_key']
            })
            
            # Set database and table name
            relationships[table_name]['database'] = row['table_catalog']
            relationships[table_name]['table_schema'] = row['table_schema']
            relationships[table_name]['table_name'] = table_name
        
        # Process explicit foreign key relationships
        for _, row in df.iterrows():
            table_name = row['table_name']
            if pd.notna(row['referenced_table']) and pd.notna(row['referenced_column']):
                referenced_table = row['referenced_table']
                shared_column = [row['column_name'], row['referenced_column']]
                
                # Add relationship to current table
                if shared_column not in relationships[table_name]['related_tables'][referenced_table]['explicit_refs']:
                    relationships[table_name]['related_tables'][referenced_table]['explicit_refs'].append(shared_column)
                
                # Add reverse relationship
                if shared_column[::-1] not in relationships[referenced_table]['related_tables'][table_name]['explicit_refs']:
                    relationships[referenced_table]['related_tables'][table_name]['explicit_refs'].append(shared_column[::-1])
        
        # Process implicit relationships (matching column names)
        processed_pairs = set()  # To avoid processing same table pair twice
        
        for table1 in table_columns:
            for table2 in table_columns:
                if table1 >= table2:  # Skip self-relationships and processed pairs
                    continue
                    
                pair_key = (table1, table2)
                if pair_key in processed_pairs:
                    continue
                    
                processed_pairs.add(pair_key)
                
                # Find matching column names
                matching_columns = []
                for col1 in table_columns[table1]:
                    for col2 in table_columns[table2]:
                        if (col1['column_name'] == col2['column_name'] and 
                            col1['data_type'] == col2['data_type'] and
                            [col1['column_name'], col2['column_name']] not in 
                            relationships[table1]['related_tables'][table2]['explicit_refs']):
                            
                            matching_columns.append([col1['column_name'], col2['column_name']])
                
                # Add matching columns to relationships if found
                if matching_columns:
                    relationships[table1]['related_tables'][table2]['possible_refs'].extend(matching_columns)
                    relationships[table2]['related_tables'][table1]['possible_refs'].extend(
                        [cols[::-1] for cols in matching_columns]
                    )
        
        # Convert defaultdict to regular dict and remove empty entries
        result = []
        for table_info in relationships.values():
            related_tables_filtered = {}
            
            for related_table, refs in table_info['related_tables'].items():
                if refs['explicit_refs'] or refs['possible_refs']:
                    related_tables_filtered[related_table] = {
                        'explicit_refs': refs['explicit_refs'],
                        'possible_refs': refs['possible_refs']
                    }
            
            if related_tables_filtered:  # Only include tables that have relationships
                result.append({
                    'database': table_info['database'],
                    'table_schema': table_info['table_schema'],
                    'table_name': table_info['table_name'],
                    'related_tables': related_tables_filtered
                })

        final_result = self.format_relationships(result)
        
        return final_result
    
    def format_relationships(self,relationships):
        """
        Print table relationships in a readable format.
        """
        relationship_docs = []

        for relation in relationships:

            doc_str = f"""
Database: {relation['database']}
Table Schema: {relation['table_schema']}
Table: {relation['table_name']}
Related Tables:\n"""
            for related_table, refs in relation['related_tables'].items():
                doc_str+=f"  {related_table}:\n"
                if refs['explicit_refs']:
                    doc_str+="    Explicit References (Foreign Keys):\n"
                    for ref in refs['explicit_refs']:
                        doc_str+=f"      - {ref[0]} → {ref[1]}\n"
                if refs['possible_refs']:
                    doc_str+="    Possible References (Matching Columns):\n"
                    for ref in refs['possible_refs']:
                        doc_str+=f"      - {ref[0]} ≈ {ref[1]}\n"
            
            relationship_docs.append({"database": relation['database'],"table_schema":relation['table_schema'],"table_name": relation['table_name'],'relation':doc_str.strip()})

        return relationship_docs

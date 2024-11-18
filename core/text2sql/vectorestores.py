# Import client library
from qdrant_client import QdrantClient
from tqdm import tqdm
import os,hashlib
import uuid
from typing import Union
from core.text2sql.reranker import DocumentReranker

class QdrantVectorStore:
    
    def __init__(self,db_location=None,url="http://3.109.124.224:6333",collection_name="Text2SQL",dense_model="sentence-transformers/all-MiniLM-L6-v2",sparse_model = "prithivida/Splade_PP_en_v1",hybird=True,enable_rerank=True) -> None:
        
        self.collection_name=collection_name

        self.enable_rerank = enable_rerank

        if self.enable_rerank:

            self.reranker = DocumentReranker()
        
        if not db_location:

            self.client_qdrant = QdrantClient(url=url)

        else:

            self.client_qdrant = QdrantClient(location=db_location)

        self.client_qdrant.set_model(dense_model)
        # comment this line to use dense vectors only
        if hybird:
            self.client_qdrant.set_sparse_model(sparse_model)

            if not self.client_qdrant.collection_exists(self.collection_name):
                self.client_qdrant.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=self.client_qdrant.get_fastembed_vector_params(),
                    # comment this line to use dense vectors only
                    sparse_vectors_config=self.client_qdrant.get_fastembed_sparse_vector_params(),  
                )
        else:
            if not self.client_qdrant.collection_exists(self.collection_name):

                self.client_qdrant.recreate_collection(
                    collection_name=self.collection_name,
                    vectors_config=self.client_qdrant.get_fastembed_vector_params()
                )

    def add_documents_to_schema_details(self,documents,ids,metadata=[],collection_name="Text2SQL"):

        if not len(ids):

            ids =[self._deterministic_uuid(i) for i in documents]
            
        return self.client_qdrant.add(
        collection_name=collection_name,
        documents=documents,
        ids=tqdm(range(len(documents))),
        metadata=metadata)

    def get_relavant_documents(self, texts: list,collection_name:str="Text2SQL",top_n_similar_docs:int=200,filtered_tables:int=2):

        if top_n_similar_docs>self.client_qdrant.count("Text2SQL").count:

            top_n_similar_docs=self.client_qdrant.count("Text2SQL").count

        final_metadata_id = set()

        final_metadata_schema = []

        # per_question_schemas = int(filtered_tables/len(texts))

        for text in texts:

            search_result = self.client_qdrant.query(
                collection_name=collection_name,
                query_text=text,
                limit=top_n_similar_docs, 
            )

            metadata = [{"id":hit.id,"text_data":hit.metadata['text_data'],"table_id":hit.metadata['table_id'],"common_columns":hit.metadata['common_columns']} for hit in search_result]
            
            if self.enable_rerank:

                metadata = self.reranker.rerank_documents(text,metadata)

            sub_metadata_schema = []

            for schema in metadata:

                if len(sub_metadata_schema)<filtered_tables:

                    if schema['table_id'] not in final_metadata_id:

                        final_metadata_id.add(schema['table_id'])

                        sub_metadata_schema.append((schema['text_data'],schema['common_columns']))

                else:

                    final_metadata_schema.extend(sub_metadata_schema)

                    break


        return [{"text_data": i,"common_columns":j }  for i, j in list(final_metadata_schema)]

        # return metadata
    
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
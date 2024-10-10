
# ------------------------------------------------- Chroma Vector Store -------------------------------- #

import sys
sys.dont_write_bytecode =True

import chromadb
from chromadb.db.base import UniqueConstraintError
from chromadb.utils import embedding_functions
import uuid
import os

os.environ['ALLOW_RESET']='TRUE'

class ChromaStore:
    def __init__(self,store_id , embedding_model_name='all-MiniLM-L6-v2'):
        self.client = chromadb.PersistentClient(f"chroma_db/{store_id}")  # data stored in 'db' folder
        # em = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="Huffon/sentence-klue-roberta-base")
        self.em = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=embedding_model_name)

    def add_documents(self,documents,ids,meta_data,collection_name='sample'):

        try:
            self.collection = self.client.create_collection(name=collection_name,embedding_function=self.em)
        except UniqueConstraintError:  # already exist collection
            self.client.reset()
            self.collection = self.client.create_collection(name=collection_name,embedding_function=self.em)

        self.collection.add(
                documents = documents,
                ids = ids,
                metadatas=meta_data
            )
        return "Documents added successfully"
        
    def get_relavant_documents(self,query,no_of_docs=10):
        results = self.collection.query(
                                query_texts=query,
                                n_results=no_of_docs)
        return results
    
    def reset(self):

        self.client.reset()

        return "Deleted Existing Data....."

# ------------------------------------------------- Qdrant Vector Store -------------------------------- #

# Import client library
# from qdrant_client import QdrantClient
# from tqdm import tqdm

# class QdrantVectorStore:
#     def __init__(self,db_location="qdrant",dense_model="sentence-transformers/all-MiniLM-L6-v2",sparse_model = "prithivida/Splade_PP_en_v1",hybird=True) -> None:
        
#         self.client = QdrantClient(path=f"vector_stores/{db_location}")

#         self.client.set_model(dense_model)
#         # comment this line to use dense vectors only
#         if hybird:
#             self.client.set_sparse_model(sparse_model)

#             self.client.recreate_collection(
#                 collection_name="schema_details",
#                 vectors_config=self.client.get_fastembed_vector_params(),
#                 # comment this line to use dense vectors only
#                 sparse_vectors_config=self.client.get_fastembed_sparse_vector_params(),  
#             )
#         else:

#             self.client.recreate_collection(
#                 collection_name="schema_details",
#                 vectors_config=self.client.get_fastembed_vector_params()
#             )

#     def add_documents_to_schema_details(self,documents,ids,collection_name="schema_details"):
#         self.client.add(
#         collection_name=collection_name,
#         documents=documents,
#         ids=tqdm(ids))

#     def get_relavant_documents(self, text: str,collection_name:str="schema_details",top_n_similar_docs=6):
#         search_result = self.client.query(
#             collection_name=collection_name,
#             query_text=text,
#             limit=top_n_similar_docs, 
#         )
#         metadata = [{"id":hit.id,"document":hit.metadata['document']} for hit in search_result]
#         return metadata
    
    
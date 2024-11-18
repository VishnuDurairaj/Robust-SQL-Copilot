from typing import List
from flashrank import Ranker, RerankRequest

class DocumentReranker:
    def __init__(self, model_name: str="ms-marco-MiniLM-L-12-v2", cache_dir: str="/opt", threshold=0.5,max_length=512):
        
        self.threshold = threshold

        self.max_length =max_length

        self.ranker = Ranker(model_name=model_name, cache_dir=cache_dir,max_length=self.max_length)

    def rerank_documents(self, query: str, documents: List[dict]) -> List[str]:

        for doc in  documents:

            doc['text'] = doc['text_data']

        # Create the rerank request with the query and documents
        rerank_request = RerankRequest(query=query, passages=documents)
        
        # Perform reranking
        reranked_docs = self.ranker.rerank(rerank_request)
                
        return reranked_docs

# reranker = DocumentReranker()
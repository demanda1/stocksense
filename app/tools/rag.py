from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.tools.news import get_news

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

def build_news_index(ticker: str) -> Chroma:
    docs = get_news(ticker)
    chunks = []
    for d in docs:
        chunks.extend(splitter.split_text(d))
    store = Chroma.from_texts(
        chunks, embeddings, collection_name=f"news_{ticker.lower()}")
    return store

def retrieve(store: Chroma, query: str, k: int = 5) -> list[str]:
    return [d.page_content for d in store.similarity_search(query, k=k)]


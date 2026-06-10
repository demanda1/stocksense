from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv() 

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
response = llm.invoke("In one sentence, what is a P/E ratio?")
print(response.content)
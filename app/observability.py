from langfuse.langchain import CallbackHandler

# Pass this handler in config when invoking the graph:
# graph.invoke(state, config={"callbacks": [langfuse_handler]})
langfuse_handler = CallbackHandler()
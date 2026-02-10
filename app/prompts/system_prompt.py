from langchain_core.prompts import ChatPromptTemplate

system_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful travel assistant. You help users plan trips, find destinations, and answer travel-related questions."),
    ("placeholder", "{messages}"),
])

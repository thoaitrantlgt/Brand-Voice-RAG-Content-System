from crewai import Agent, LLM
from pydantic import BaseModel

print("CrewAI LLM type:", type(LLM))

try:
    from langchain_huggingface import HuggingFacePipeline
    pipe = HuggingFacePipeline.from_model_id(model_id="gpt2", task="text-generation")
    print("Is pipe BaseLLM?", isinstance(pipe, BaseModel))
except Exception as e:
    print(e)

try:
    agent = Agent(
        role="Test",
        goal="Test",
        backstory="Test",
        llm="gpt2"
    )
    print("Agent created with string LLM.")
except Exception as e:
    print(e)

try:
    agent = Agent(
        role="Test",
        goal="Test",
        backstory="Test",
        llm=pipe
    )
    print("Agent created with HuggingFacePipeline.")
except Exception as e:
    print("Agent HuggingFacePipeline Failed:", e)

try:
    from langchain_huggingface import ChatHuggingFace
    chat_model = ChatHuggingFace(llm=pipe)
    agent = Agent(
        role="Test",
        goal="Test",
        backstory="Test",
        llm=chat_model
    )
    print("Agent created with ChatHuggingFace.")
except Exception as e:
    print("Agent ChatHuggingFace Failed:", e)

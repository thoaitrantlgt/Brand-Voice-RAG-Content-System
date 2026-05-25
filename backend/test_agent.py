from crewai import Agent
from langchain_community.llms.huggingface_pipeline import HuggingFacePipeline
try:
    pipe = HuggingFacePipeline.from_model_id(model_id="gpt2", task="text-generation", pipeline_kwargs={"max_new_tokens": 10})
    agent = Agent(
        role="Test",
        goal="Test",
        backstory="Test",
        llm=pipe
    )
    print("Agent created successfully with HuggingFacePipeline")
except Exception as e:
    import traceback
    traceback.print_exc()

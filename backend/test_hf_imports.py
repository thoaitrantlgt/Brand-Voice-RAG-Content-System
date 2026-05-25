import sys
try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    print("transformers imported successfully")
except Exception as e:
    print("Error importing transformers:", type(e), e)

try:
    from langchain_community.llms.huggingface_pipeline import HuggingFacePipeline
    print("HuggingFacePipeline imported successfully")
except Exception as e:
    print("Error importing HuggingFacePipeline:", type(e), e)

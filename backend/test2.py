import sys
import traceback

try:
    print("Trying to import transformers...")
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    print("Successfully imported transformers.")
except Exception as e:
    print("Error importing transformers:")
    traceback.print_exc()

try:
    print("Trying to import HuggingFacePipeline from langchain_community...")
    from langchain_community.llms.huggingface_pipeline import HuggingFacePipeline
    print("Successfully imported HuggingFacePipeline from langchain_community.")
except Exception as e:
    print("Error importing HuggingFacePipeline from langchain_community:")
    traceback.print_exc()

try:
    print("Trying to import HuggingFacePipeline from langchain_huggingface...")
    from langchain_huggingface import HuggingFacePipeline
    print("Successfully imported HuggingFacePipeline from langchain_huggingface.")
except Exception as e:
    print("Error importing HuggingFacePipeline from langchain_huggingface:")
    traceback.print_exc()

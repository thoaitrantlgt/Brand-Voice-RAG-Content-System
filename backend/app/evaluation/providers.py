from __future__ import annotations

import json
import re
from typing import Any


def _extract_json(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text


def create_deepeval_openai_model(
    *, model: str, base_url: str, api_key: str, max_tokens: int = 2048
) -> Any:
    try:
        from deepeval.models import DeepEvalBaseLLM
        from openai import AsyncOpenAI, OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "DeepEval dependencies are missing. Install backend/requirements-eval.txt."
        ) from exc

    class OpenAICompatibleDeepEvalModel(DeepEvalBaseLLM):
        def __init__(self) -> None:
            self._model_name = model
            self._base_url = base_url
            self._api_key = api_key
            self._max_tokens = max_tokens
            self._async_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            super().__init__(model=model)

        def load_model(self) -> Any:
            return OpenAI(api_key=self._api_key, base_url=self._base_url)

        def _parse(self, content: str, schema: Any | None) -> Any:
            if schema is None:
                return content
            payload = json.loads(_extract_json(content))
            return schema.model_validate(payload)

        def _request_options(self) -> dict[str, Any]:
            options: dict[str, Any] = {"max_tokens": self._max_tokens}
            if not self._model_name.startswith(("gemini-3.6", "gemini-3.5-flash-lite")):
                options["temperature"] = 0
            return options

        def generate(self, prompt: str, schema: Any | None = None, **_kwargs: Any) -> Any:
            response = self.model.chat.completions.create(
                model=self._model_name,
                messages=[{"role": "user", "content": prompt}],
                **self._request_options(),
            )
            return self._parse(response.choices[0].message.content or "", schema)

        async def a_generate(
            self, prompt: str, schema: Any | None = None, **_kwargs: Any
        ) -> Any:
            response = await self._async_client.chat.completions.create(
                model=self._model_name,
                messages=[{"role": "user", "content": prompt}],
                **self._request_options(),
            )
            return self._parse(response.choices[0].message.content or "", schema)

        def get_model_name(self) -> str:
            return f"openai-compatible/{self._model_name}"

        def supports_structured_outputs(self) -> bool:
            return True

        def supports_temperature(self) -> bool:
            return True

    return OpenAICompatibleDeepEvalModel()


def create_ragas_openai_stack(
    *,
    model: str,
    embedding_model: str,
    base_url: str,
    api_key: str,
    max_tokens: int = 2048,
    embedding_base_url: str | None = None,
    embedding_api_key: str | None = None,
) -> tuple[Any, Any]:
    try:
        import instructor
        from langchain_openai import OpenAIEmbeddings
        from openai import OpenAI
        from ragas.embeddings.base import LangchainEmbeddingsWrapper
        from ragas.llms.base import InstructorLLM, InstructorModelArgs
    except ImportError as exc:
        raise RuntimeError(
            "Ragas dependencies are missing. Install backend/requirements-eval.txt."
        ) from exc

    client = OpenAI(api_key=api_key, base_url=base_url)
    structured_client = instructor.from_openai(
        client,
        mode=instructor.Mode.JSON_SCHEMA,
    )
    llm = InstructorLLM(
        client=structured_client,
        model=model,
        provider="openai",
        model_args=InstructorModelArgs(temperature=0, max_tokens=max_tokens),
    )
    if model.startswith(("gemini-3.6", "gemini-3.5-flash-lite")):
        llm.model_args.pop("temperature", None)
        llm.model_args.pop("top_p", None)
    embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(
            model=embedding_model,
            base_url=embedding_base_url or base_url,
            api_key=embedding_api_key or api_key,
            tiktoken_enabled=False,
            check_embedding_ctx_length=False,
        )
    )
    return llm, embeddings

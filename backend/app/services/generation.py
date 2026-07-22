from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import Protocol

from openai import APITimeoutError

from app.core.config import Settings
from app.services.citation_validator import CitationValidation, validate_citations
from app.services.prompting import add_citation_correction


class GenerationProvider(Protocol):
    async def complete(self, messages: Sequence[dict[str, str]]) -> str: ...

    async def close(self) -> None: ...


GenerationProviderFactory = Callable[[Settings], GenerationProvider]


class GenerationUnavailableError(RuntimeError):
    pass


class GenerationTimeoutError(RuntimeError):
    pass


class GenerationProviderError(RuntimeError):
    pass


class GenerationInvalidResponseError(RuntimeError):
    pass


class OpenAIChatProvider:
    def __init__(self, settings: Settings) -> None:
        from openai import AsyncOpenAI

        api_key = (
            settings.generation_api_key.get_secret_value()
            if settings.generation_api_key is not None
            else "local-openai-compatible"
        )
        self._model = str(settings.generation_model)
        self._max_tokens = settings.generation_max_output_tokens
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.generation_base_url,
            timeout=float(settings.generation_timeout_seconds),
            max_retries=1,
        )

    async def complete(self, messages: Sequence[dict[str, str]]) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=list(messages),  # type: ignore[arg-type]
            temperature=0,
            max_tokens=self._max_tokens,
        )
        content = response.choices[0].message.content if response.choices else None
        return content or ""

    async def close(self) -> None:
        await self._client.close()


class GenerationService:
    def __init__(
        self,
        settings: Settings,
        provider: GenerationProvider | None,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self._semaphore = asyncio.Semaphore(settings.generation_max_concurrency)

    @property
    def ready(self) -> bool:
        return self.settings.generation_configuration_ready and self.provider is not None

    async def generate_validated(
        self,
        messages: Sequence[dict[str, str]],
        *,
        allowed_labels: Sequence[str],
    ) -> tuple[str, CitationValidation]:
        if not self.ready or self.provider is None:
            raise GenerationUnavailableError("Generation is disabled or not configured.")
        answer = await self._complete(messages)
        validation = validate_citations(answer, allowed_labels)
        if validation.valid:
            return answer, validation
        corrected = add_citation_correction(messages, answer, allowed_labels)
        answer = await self._complete(corrected)
        validation = validate_citations(answer, allowed_labels)
        if not validation.valid:
            raise GenerationInvalidResponseError(
                "The generation provider did not return a grounded answer with valid citations."
            )
        return answer, validation

    async def _complete(self, messages: Sequence[dict[str, str]]) -> str:
        assert self.provider is not None
        try:
            async with self._semaphore:
                answer = await asyncio.wait_for(
                    self.provider.complete(messages),
                    timeout=self.settings.generation_timeout_seconds,
                )
        except TimeoutError as exc:
            raise GenerationTimeoutError("The generation provider timed out.") from exc
        except GenerationInvalidResponseError:
            raise
        except Exception as exc:
            if isinstance(exc, APITimeoutError):
                raise GenerationTimeoutError("The generation provider timed out.") from exc
            raise GenerationProviderError("The generation provider request failed.") from exc
        if not answer.strip():
            raise GenerationInvalidResponseError("The generation provider returned no answer.")
        return answer.strip()

    async def close(self) -> None:
        if self.provider is not None:
            await self.provider.close()


def build_generation_service(
    settings: Settings,
    provider_factory: GenerationProviderFactory | None = None,
) -> GenerationService:
    provider: GenerationProvider | None = None
    if settings.generation_configuration_ready:
        provider = (provider_factory or OpenAIChatProvider)(settings)
    return GenerationService(settings, provider)

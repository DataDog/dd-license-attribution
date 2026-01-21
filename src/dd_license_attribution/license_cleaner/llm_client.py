# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

# LLM client interface for converting license text to SPDX identifiers

import logging
from typing import Protocol

import anthropic
import openai

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol for LLM clients that can convert license text to SPDX identifiers."""

    def convert_to_spdx(self, license_text: str) -> str:
        """
        Convert a long license description to a valid SPDX identifier.

        Args:
            license_text: The long license description text

        Returns:
            The SPDX identifier (e.g., "BSD-3-Clause", "MIT", "Apache-2.0")
        """
        ...


class OpenAIClient:
    """OpenAI-based LLM client for license text conversion."""

    def __init__(self, api_key: str, model: str = "gpt-4") -> None:
        """
        Initialize the OpenAI client.

        Args:
            api_key: OpenAI API key
            model: Model to use (default: gpt-4)
        """
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        logger.debug("Initialized OpenAI client with model: %s", model)

    def convert_to_spdx(self, license_text: str) -> str:
        """Convert license text to SPDX identifier using OpenAI."""
        prompt = self._build_prompt(license_text)

        logger.debug("Requesting SPDX conversion from OpenAI")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a license identification expert. Your task is to identify the SPDX license identifier from license text. Respond ONLY with the SPDX identifier, nothing else. If you cannot identify the license, respond with 'UNKNOWN'.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=50,
            )

            spdx_id = response.choices[0].message.content
            if spdx_id:
                spdx_id = spdx_id.strip()
                logger.debug("OpenAI returned SPDX identifier: %s", spdx_id)
                return spdx_id
            else:
                logger.warning("OpenAI returned empty response")
                return "UNKNOWN"

        except openai.BadRequestError as e:
            # Handle HTTP errors (non-200 status codes)
            # Special handling for context length exceeded errors
            # Check multiple possible locations for the error code
            is_context_error = False

            # Check if error code is in the exception body
            if hasattr(e, "body") and isinstance(e.body, dict):
                error_dict = e.body.get("error", {})
                if isinstance(error_dict, dict):
                    if error_dict.get("code") == "context_length_exceeded":
                        is_context_error = True

            # Also check the error message for context length indicators
            if not is_context_error and hasattr(e, "message"):
                error_msg = str(e.message).lower()
                if "context length" in error_msg and "exceeded" in error_msg:
                    is_context_error = True

            if is_context_error:
                logger.info(
                    "OpenAI context length exceeded for license text, skipping: %s",
                    str(e),
                )
                return "UNKNOWN"

            logger.error(
                "OpenAI API error - Status code %s: %s",
                e.status_code,
                e.message,
                exc_info=True,
            )
            raise
        except openai.RateLimitError as e:
            logger.error("OpenAI rate limit exceeded: %s", e, exc_info=True)
            raise
        except openai.APIConnectionError as e:
            logger.error("OpenAI API connection error: %s", e, exc_info=True)
            raise
        except openai.AuthenticationError as e:
            logger.error(
                "OpenAI authentication error (invalid API key): %s", e, exc_info=True
            )
            raise
        except openai.APIError as e:
            # Catch-all for other OpenAI API errors
            logger.error("OpenAI API error: %s", e, exc_info=True)
            raise
        except Exception as e:
            logger.error("Unexpected error calling OpenAI API: %s", e, exc_info=True)
            raise

    def _build_prompt(self, license_text: str) -> str:
        """Build the prompt for the LLM."""
        return f"""Identify the SPDX license identifier for the following license text.
Respond with ONLY the SPDX identifier (e.g., "BSD-3-Clause", "MIT", "Apache-2.0").

License text:
{license_text}

SPDX identifier:"""


class AnthropicClient:
    """Anthropic Claude-based LLM client for license text conversion."""

    def __init__(self, api_key: str, model: str = "claude-3-7-sonnet-20250219") -> None:
        """
        Initialize the Anthropic client.

        Args:
            api_key: Anthropic API key
            model: Model to use (default: claude-3-7-sonnet-20250219)
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        logger.debug("Initialized Anthropic client with API key: %s", api_key)
        self.model = model
        logger.debug("Initialized Anthropic client with model: %s", model)

    def convert_to_spdx(self, license_text: str) -> str:
        """Convert license text to SPDX identifier using Anthropic Claude."""
        prompt = self._build_prompt(license_text)

        logger.debug("Requesting SPDX conversion from Anthropic")
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=50,
                temperature=0,
                system="You are a license identification expert. Your task is to identify the SPDX license identifier from license text. Respond ONLY with the SPDX identifier, nothing else. If you cannot identify the license, respond with 'UNKNOWN'.",
                messages=[{"role": "user", "content": prompt}],
            )

            # Get text from response (only TextBlock has .text attribute)
            content_block = response.content[0]
            if hasattr(content_block, "text"):
                spdx_id = content_block.text
            else:
                spdx_id = None

            if spdx_id:
                spdx_id = spdx_id.strip()
                logger.debug("Anthropic returned SPDX identifier: %s", spdx_id)
                return spdx_id
            else:
                logger.warning("Anthropic returned empty response")
                return "UNKNOWN"
        except anthropic.RateLimitError as e:
            logger.error("Anthropic rate limit exceeded: %s", e, exc_info=True)
            raise
        except anthropic.APIConnectionError as e:
            logger.error("Anthropic API connection error: %s", e, exc_info=True)
            raise
        except anthropic.AuthenticationError as e:
            logger.error(
                "Anthropic authentication error (invalid API key): %s",
                e,
                exc_info=True,
            )
            raise
        except anthropic.APIStatusError as e:
            # Handle HTTP errors (non-200 status codes)
            # Special handling for context length exceeded errors
            is_context_error = False

            # Check if error message indicates context length issue
            if hasattr(e, "body") and isinstance(e.body, dict):
                error_dict = e.body.get("error", {})
                if isinstance(error_dict, dict):
                    error_message = error_dict.get("message", "")
                    if "maximum context length" in error_message.lower():
                        is_context_error = True

            # Also check the error message directly
            if not is_context_error and hasattr(e, "message"):
                error_msg = str(e.message).lower()
                if "context" in error_msg and (
                    "length" in error_msg or "token" in error_msg
                ):
                    is_context_error = True

            if is_context_error:
                logger.info(
                    "Anthropic context length exceeded for license text, skipping: %s",
                    str(e),
                )
                return "UNKNOWN"

            logger.error(
                "Anthropic API error - Status code %s: %s",
                e.status_code,
                e.message,
                exc_info=True,
            )
            raise
        except anthropic.APIError as e:
            # Catch-all for other Anthropic API errors
            logger.error("Anthropic API error: %s", e, exc_info=True)
            raise
        except Exception as e:
            logger.error("Unexpected error calling Anthropic API: %s", e, exc_info=True)
            raise

    def _build_prompt(self, license_text: str) -> str:
        """Build the prompt for the LLM."""
        return f"""Identify the SPDX license identifier for the following license text.
Respond with ONLY the SPDX identifier (e.g., "BSD-3-Clause", "MIT", "Apache-2.0").

License text:
{license_text}

SPDX identifier:"""


def create_llm_client(
    provider: str, api_key: str, model: str | None = None
) -> LLMClient:
    """
    Factory function to create an LLM client based on provider.

    Args:
        provider: LLM provider ("openai" or "anthropic")
        api_key: API key for the provider
        model: Optional model name to use (uses default if not specified)

    Returns:
        An LLM client instance

    Raises:
        ValueError: If provider is not supported
    """
    provider_lower = provider.lower()

    if provider_lower == "openai":
        if model:
            return OpenAIClient(api_key=api_key, model=model)
        return OpenAIClient(api_key=api_key)
    elif provider_lower == "anthropic":
        if model:
            return AnthropicClient(api_key=api_key, model=model)
        return AnthropicClient(api_key=api_key)
    else:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. Supported providers: openai, anthropic"
        )

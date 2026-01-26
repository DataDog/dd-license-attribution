# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

"""Contract tests for OpenAI and Anthropic LLM APIs.

These tests validate the structure and behavior of OpenAI and Anthropic APIs
that our code depends on. They ensure that API changes don't break our assumptions.

Note: These tests make real API calls and require valid API keys:
- OPENAI_API_KEY environment variable for OpenAI tests
- ANTHROPIC_API_KEY environment variable for Anthropic tests

Tests will be skipped if API keys are not available.
These tests will incur minimal API costs (using small max_tokens values).
"""

import os

import anthropic
import openai
import pytest


class TestOpenAIAPIContract:
    """Validate OpenAI API endpoint contracts and error handling."""

    @pytest.fixture
    def openai_client(self) -> openai.OpenAI:
        """Create OpenAI client for testing."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY environment variable not set")
        return openai.OpenAI(api_key=api_key)

    def test_chat_completions_returns_expected_structure(
        self, openai_client: openai.OpenAI
    ) -> None:
        """Ensure OpenAI chat completions API returns expected response structure.

        We depend on:
        - response.choices[0].message.content containing the response text
        - The ability to set model, messages, temperature, and max_tokens
        """
        # Make a minimal API call to keep costs low
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",  # Use the cheapest model
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Respond with only 'OK'.",
                },
                {"role": "user", "content": "Test"},
            ],
            temperature=0,
            max_tokens=5,  # Minimal tokens to reduce cost
        )

        # Validate response structure
        assert hasattr(response, "choices"), "Response should have 'choices' attribute"
        assert len(response.choices) > 0, "Response should have at least one choice"

        # Validate first choice structure
        first_choice = response.choices[0]
        assert hasattr(
            first_choice, "message"
        ), "Choice should have 'message' attribute"

        # Validate message structure
        message = first_choice.message
        assert hasattr(message, "content"), "Message should have 'content' attribute"
        assert isinstance(
            message.content, str
        ), "Message content should be a string or None"

    def test_authentication_error_is_raised_for_invalid_key(self) -> None:
        """Ensure OpenAI raises AuthenticationError for invalid API keys.

        We depend on catching openai.AuthenticationError for invalid credentials.
        """
        invalid_client = openai.OpenAI(api_key="invalid_key_12345")

        with pytest.raises(openai.AuthenticationError) as exc_info:
            invalid_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=5,
            )

        # Validate error has expected attributes
        error = exc_info.value
        assert hasattr(error, "status_code"), "Error should have status_code attribute"
        assert error.status_code == 401, "Authentication error should return status 401"

    def test_not_found_error_structure(self, openai_client: openai.OpenAI) -> None:
        """Ensure OpenAI NotFoundError has expected structure for invalid models.

        We depend on OpenAI error types having consistent structure:
        - error.status_code attribute
        - error.message attribute
        - error.body dict with 'error' field
        """
        # Trigger a NotFoundError with an invalid model
        with pytest.raises(openai.NotFoundError) as exc_info:
            openai_client.chat.completions.create(
                model="invalid-model-xyz-123",
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=5,
            )

        # Validate error structure
        error = exc_info.value
        assert hasattr(error, "status_code"), "Error should have status_code attribute"
        assert error.status_code == 404, "NotFoundError should return status 404"
        assert hasattr(error, "message"), "Error should have message attribute"
        assert hasattr(error, "body"), "Error should have body attribute"

        # Validate body structure (if present)
        if error.body:
            assert isinstance(error.body, dict), "Error body should be a dict"
            assert "error" in error.body, "Error body should contain 'error' field"

    def test_error_types_exist(self) -> None:
        """Ensure all OpenAI error types we depend on exist and are importable.

        We catch the following exception types in our code:
        - BadRequestError (for context length exceeded)
        - NotFoundError (for invalid models/resources)
        - RateLimitError
        - APIConnectionError
        - AuthenticationError
        - APIError (base error type)
        """
        # Validate error types are defined
        assert hasattr(
            openai, "BadRequestError"
        ), "openai.BadRequestError should be defined"
        assert hasattr(
            openai, "NotFoundError"
        ), "openai.NotFoundError should be defined"
        assert hasattr(
            openai, "RateLimitError"
        ), "openai.RateLimitError should be defined"
        assert hasattr(
            openai, "APIConnectionError"
        ), "openai.APIConnectionError should be defined"
        assert hasattr(
            openai, "AuthenticationError"
        ), "openai.AuthenticationError should be defined"
        assert hasattr(openai, "APIError"), "openai.APIError should be defined"

        # Validate error types are Exception subclasses
        assert issubclass(
            openai.BadRequestError, Exception
        ), "BadRequestError should be an Exception"
        assert issubclass(
            openai.NotFoundError, Exception
        ), "NotFoundError should be an Exception"
        assert issubclass(
            openai.RateLimitError, Exception
        ), "RateLimitError should be an Exception"
        assert issubclass(
            openai.APIConnectionError, Exception
        ), "APIConnectionError should be an Exception"
        assert issubclass(
            openai.AuthenticationError, Exception
        ), "AuthenticationError should be an Exception"
        assert issubclass(openai.APIError, Exception), "APIError should be an Exception"


class TestAnthropicAPIContract:
    """Validate Anthropic API endpoint contracts and error handling."""

    @pytest.fixture
    def anthropic_client(self) -> anthropic.Anthropic:
        """Create Anthropic client for testing."""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY environment variable not set")
        return anthropic.Anthropic(api_key=api_key)

    def test_messages_create_returns_expected_structure(
        self, anthropic_client: anthropic.Anthropic
    ) -> None:
        """Ensure Anthropic messages API returns expected response structure.

        We depend on:
        - response.content[0].text containing the response text
        - The ability to set model, max_tokens, temperature, system, and messages
        """
        # Make a minimal API call to keep costs low
        response = anthropic_client.messages.create(
            model="claude-3-5-haiku-20241022",  # Use a cost-effective model
            max_tokens=10,  # Minimal tokens to reduce cost
            temperature=0,
            system="You are a helpful assistant. Respond with only 'OK'.",
            messages=[{"role": "user", "content": "Test"}],
        )

        # Validate response structure
        assert hasattr(response, "content"), "Response should have 'content' attribute"
        assert (
            len(response.content) > 0
        ), "Response should have at least one content block"

        # Validate first content block structure
        first_content = response.content[0]
        assert hasattr(
            first_content, "text"
        ), "Content block should have 'text' attribute"
        assert isinstance(
            first_content.text, str
        ), "Content text should be a string when present"

    def test_authentication_error_is_raised_for_invalid_key(self) -> None:
        """Ensure Anthropic raises AuthenticationError for invalid API keys.

        We depend on catching anthropic.AuthenticationError for invalid credentials.
        """
        invalid_client = anthropic.Anthropic(api_key="invalid_key_12345")

        with pytest.raises(anthropic.AuthenticationError) as exc_info:
            invalid_client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=10,
                messages=[{"role": "user", "content": "Test"}],
            )

        # Validate error has expected attributes
        error = exc_info.value
        assert hasattr(error, "status_code"), "Error should have status_code attribute"
        assert error.status_code == 401, "Authentication error should return status 401"

    def test_api_status_error_structure(
        self, anthropic_client: anthropic.Anthropic
    ) -> None:
        """Ensure Anthropic APIStatusError has expected structure.

        We depend on:
        - anthropic.APIStatusError exception type
        - error.status_code attribute
        - error.body dict with 'error' field for error details
        - error.message attribute
        """
        # Try to trigger an APIStatusError with an invalid model
        with pytest.raises(anthropic.APIStatusError) as exc_info:
            anthropic_client.messages.create(
                model="invalid-model-xyz-123",
                max_tokens=10,
                messages=[{"role": "user", "content": "Test"}],
            )

        # Validate error structure
        error = exc_info.value
        assert hasattr(error, "status_code"), "Error should have status_code attribute"
        assert hasattr(error, "message"), "Error should have message attribute"
        assert hasattr(error, "body"), "Error should have body attribute"

        # Validate body structure (if present)
        if error.body:
            assert isinstance(error.body, dict), "Error body should be a dict"

    def test_error_types_exist(self) -> None:
        """Ensure all Anthropic error types we depend on exist and are importable.

        We catch the following exception types in our code:
        - RateLimitError
        - APIConnectionError
        - AuthenticationError
        - APIStatusError (for HTTP errors including context length)
        - APIError (base error type)
        """
        # Validate error types are defined
        assert hasattr(
            anthropic, "RateLimitError"
        ), "anthropic.RateLimitError should be defined"
        assert hasattr(
            anthropic, "APIConnectionError"
        ), "anthropic.APIConnectionError should be defined"
        assert hasattr(
            anthropic, "AuthenticationError"
        ), "anthropic.AuthenticationError should be defined"
        assert hasattr(
            anthropic, "APIStatusError"
        ), "anthropic.APIStatusError should be defined"
        assert hasattr(anthropic, "APIError"), "anthropic.APIError should be defined"

        # Validate error types are Exception subclasses
        assert issubclass(
            anthropic.RateLimitError, Exception
        ), "RateLimitError should be an Exception"
        assert issubclass(
            anthropic.APIConnectionError, Exception
        ), "APIConnectionError should be an Exception"
        assert issubclass(
            anthropic.AuthenticationError, Exception
        ), "AuthenticationError should be an Exception"
        assert issubclass(
            anthropic.APIStatusError, Exception
        ), "APIStatusError should be an Exception"
        assert issubclass(
            anthropic.APIError, Exception
        ), "APIError should be an Exception"

    def test_content_block_types(self, anthropic_client: anthropic.Anthropic) -> None:
        """Ensure Anthropic response content blocks have the expected type structure.

        We depend on checking hasattr(content_block, 'text') to determine
        if the content block is a TextBlock that contains text.
        """
        response = anthropic_client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say 'test'"}],
        )

        # Validate we can check for text attribute
        content_block = response.content[0]
        has_text = hasattr(content_block, "text")
        assert isinstance(
            has_text, bool
        ), "hasattr check should return a boolean for text attribute"

        # For text responses, the text attribute should exist and be accessible
        if has_text:
            # Access text using getattr to satisfy mypy (same pattern as our actual code)
            text_value = getattr(content_block, "text", None)
            assert isinstance(
                text_value, str
            ), "Text attribute should be a string when present"

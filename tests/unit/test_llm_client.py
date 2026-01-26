# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

# Unit tests for LLM client

from unittest.mock import Mock, patch

import pytest

from dd_license_attribution.license_cleaner.llm_client import (
    AnthropicClient,
    OpenAIClient,
    create_llm_client,
)


class TestOpenAIClient:
    """Test OpenAI client for license conversion."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        self.mock_openai = Mock()
        self.api_key = "test-api-key"
        self.model = "gpt-4"

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_initialization_with_default_model(self, mock_openai_class: Mock) -> None:
        """Test OpenAI client initialization with default model."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(api_key=self.api_key)

        mock_openai_class.assert_called_once_with(api_key=self.api_key)
        assert client.model == "gpt-4"
        assert client.client == mock_client

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_initialization_with_custom_model(self, mock_openai_class: Mock) -> None:
        """Test OpenAI client initialization with custom model."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        custom_model = "gpt-3.5-turbo"

        client = OpenAIClient(api_key=self.api_key, model=custom_model)

        mock_openai_class.assert_called_once_with(api_key=self.api_key)
        assert client.model == custom_model

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_convert_to_spdx_success(self, mock_openai_class: Mock) -> None:
        """Test successful conversion of license text to SPDX license expression."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Mock the API response
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "BSD-3-Clause"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        client = OpenAIClient(api_key=self.api_key)
        license_text = "BSD 3-Clause License\n\nCopyright (c) 2022..."

        result = client.convert_to_spdx(license_text)

        assert result == "BSD-3-Clause"
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4"
        assert call_kwargs["temperature"] == 0
        assert call_kwargs["max_tokens"] == 50
        assert len(call_kwargs["messages"]) == 2

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_convert_to_spdx_empty_response(self, mock_openai_class: Mock) -> None:
        """Test handling of empty response from API."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = None
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        client = OpenAIClient(api_key=self.api_key)
        license_text = "Some license text"

        result = client.convert_to_spdx(license_text)

        assert result == "UNKNOWN"

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_convert_to_spdx_api_error(self, mock_openai_class: Mock) -> None:
        """Test handling of API errors."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        client = OpenAIClient(api_key=self.api_key)
        license_text = "Some license text"

        with pytest.raises(Exception, match="API Error"):
            client.convert_to_spdx(license_text)

        mock_client.chat.completions.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_convert_to_spdx_api_status_error(self, mock_openai_class: Mock) -> None:
        """Test handling of HTTP status errors (non-200 responses)."""
        import openai

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Create a proper APIStatusError
        mock_client.chat.completions.create.side_effect = openai.APIStatusError(
            message="Bad Request",
            response=Mock(status_code=400),
            body={"error": {"message": "Bad Request"}},
        )

        client = OpenAIClient(api_key=self.api_key)
        license_text = "Some license text"

        with pytest.raises(openai.APIStatusError):
            client.convert_to_spdx(license_text)

        mock_client.chat.completions.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_convert_to_spdx_rate_limit_error(self, mock_openai_class: Mock) -> None:
        """Test handling of rate limit errors."""
        import openai

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = openai.RateLimitError(
            message="Rate limit exceeded",
            response=Mock(status_code=429),
            body={"error": {"message": "Rate limit exceeded"}},
        )

        client = OpenAIClient(api_key=self.api_key)
        license_text = "Some license text"

        with pytest.raises(openai.RateLimitError):
            client.convert_to_spdx(license_text)

        mock_client.chat.completions.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_convert_to_spdx_authentication_error(
        self, mock_openai_class: Mock
    ) -> None:
        """Test handling of authentication errors (invalid API key)."""
        import openai

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = openai.AuthenticationError(
            message="Invalid API key",
            response=Mock(status_code=401),
            body={"error": {"message": "Invalid API key"}},
        )

        client = OpenAIClient(api_key=self.api_key)
        license_text = "Some license text"

        with pytest.raises(openai.AuthenticationError):
            client.convert_to_spdx(license_text)

        mock_client.chat.completions.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_convert_to_spdx_connection_error(self, mock_openai_class: Mock) -> None:
        """Test handling of connection errors."""
        import openai

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = openai.APIConnectionError(
            request=Mock()
        )

        client = OpenAIClient(api_key=self.api_key)
        license_text = "Some license text"

        with pytest.raises(openai.APIConnectionError):
            client.convert_to_spdx(license_text)

        mock_client.chat.completions.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_convert_to_spdx_not_found_error(self, mock_openai_class: Mock) -> None:
        """Test handling of NotFoundError for non-existent models."""
        import openai

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        # OpenAI returns 404 NotFoundError for invalid/non-existent models
        mock_client.chat.completions.create.side_effect = openai.NotFoundError(
            message="The model `invalid-model-xyz` does not exist or you do not have access to it.",
            response=Mock(status_code=404),
            body={
                "message": "The model `invalid-model-xyz` does not exist or you do not have access to it.",
                "type": "invalid_request_error",
                "param": None,
                "code": "model_not_found",
            },
        )

        client = OpenAIClient(api_key=self.api_key)
        license_text = "Some license text"

        with pytest.raises(openai.NotFoundError):
            client.convert_to_spdx(license_text)

        mock_client.chat.completions.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_convert_to_spdx_context_length_exceeded_returns_unknown(
        self, mock_openai_class: Mock
    ) -> None:
        """Test that context length exceeded errors return UNKNOWN instead of raising."""
        import openai

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Create a context length exceeded error (BadRequestError)
        error_body = {
            "message": "This model's maximum context length is 8192 tokens. However, your messages resulted in 9306 tokens.",
            "type": "invalid_request_error",
            "param": "messages",
            "code": "context_length_exceeded",
        }
        mock_client.chat.completions.create.side_effect = openai.BadRequestError(
            message="Bad Request",
            response=Mock(status_code=400),
            body=error_body,
        )

        client = OpenAIClient(api_key=self.api_key)
        license_text = "Very long license text that exceeds context length..."

        # Should return UNKNOWN instead of raising
        result = client.convert_to_spdx(license_text)
        assert result == "UNKNOWN"

        mock_client.chat.completions.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_convert_to_spdx_strips_whitespace(self, mock_openai_class: Mock) -> None:
        """Test that response whitespace is stripped."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "  MIT  \n"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        client = OpenAIClient(api_key=self.api_key)
        result = client.convert_to_spdx("license text")

        assert result == "MIT"

        mock_client.chat.completions.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_convert_to_spdx_composite_license_expression(
        self, mock_openai_class: Mock
    ) -> None:
        """Test successful conversion to composite SPDX license expression."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "MIT OR Apache-2.0"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        client = OpenAIClient(api_key=self.api_key)
        license_text = "Dual licensed under MIT or Apache 2.0"

        result = client.convert_to_spdx(license_text)

        assert result == "MIT OR Apache-2.0"
        mock_client.chat.completions.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_convert_to_spdx_license_with_exception(
        self, mock_openai_class: Mock
    ) -> None:
        """Test successful conversion to SPDX license expression with exception."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "GPL-2.0-only WITH Classpath-exception-2.0"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        client = OpenAIClient(api_key=self.api_key)
        license_text = "GPL 2.0 with Classpath exception"

        result = client.convert_to_spdx(license_text)

        assert result == "GPL-2.0-only WITH Classpath-exception-2.0"
        mock_client.chat.completions.create.assert_called_once()


class TestAnthropicClient:
    """Test Anthropic client for license conversion."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        self.api_key = "test-api-key"
        self.model = "claude-3-7-sonnet-20250219"

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_initialization_with_default_model(
        self, mock_anthropic_class: Mock
    ) -> None:
        """Test Anthropic client initialization with default model."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        client = AnthropicClient(api_key=self.api_key)

        mock_anthropic_class.assert_called_once_with(api_key=self.api_key)
        assert client.model == "claude-3-7-sonnet-20250219"
        assert client.client == mock_client

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_initialization_with_custom_model(self, mock_anthropic_class: Mock) -> None:
        """Test Anthropic client initialization with custom model."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        custom_model = "claude-3-opus-20240229"

        client = AnthropicClient(api_key=self.api_key, model=custom_model)

        mock_anthropic_class.assert_called_once_with(api_key=self.api_key)
        assert client.model == custom_model

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_convert_to_spdx_success(self, mock_anthropic_class: Mock) -> None:
        """Test successful conversion of license text to SPDX license expression."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        # Mock the API response
        mock_response = Mock()
        mock_content = Mock()
        mock_content.text = "Apache-2.0"
        mock_response.content = [mock_content]
        mock_client.messages.create.return_value = mock_response

        client = AnthropicClient(api_key=self.api_key)
        license_text = "Apache License\nVersion 2.0..."

        result = client.convert_to_spdx(license_text)

        assert result == "Apache-2.0"
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-3-7-sonnet-20250219"
        assert call_kwargs["temperature"] == 0
        assert call_kwargs["max_tokens"] == 50
        assert len(call_kwargs["messages"]) == 1

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_convert_to_spdx_empty_response(self, mock_anthropic_class: Mock) -> None:
        """Test handling of empty response from API."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        mock_response = Mock()
        mock_content = Mock()
        mock_content.text = None
        mock_response.content = [mock_content]
        mock_client.messages.create.return_value = mock_response

        client = AnthropicClient(api_key=self.api_key)
        license_text = "Some license text"

        result = client.convert_to_spdx(license_text)

        assert result == "UNKNOWN"
        mock_client.messages.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_convert_to_spdx_api_error(self, mock_anthropic_class: Mock) -> None:
        """Test handling of API errors."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API Error")

        client = AnthropicClient(api_key=self.api_key)
        license_text = "Some license text"

        with pytest.raises(Exception, match="API Error"):
            client.convert_to_spdx(license_text)

        mock_client.messages.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_convert_to_spdx_api_status_error(self, mock_anthropic_class: Mock) -> None:
        """Test handling of HTTP status errors (non-200 responses)."""
        import anthropic

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        # Create a proper APIStatusError
        mock_client.messages.create.side_effect = anthropic.APIStatusError(
            message="Bad Request",
            response=Mock(status_code=400),
            body={"error": {"message": "Bad Request"}},
        )

        client = AnthropicClient(api_key=self.api_key)
        license_text = "Some license text"

        with pytest.raises(anthropic.APIStatusError):
            client.convert_to_spdx(license_text)

        mock_client.messages.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_convert_to_spdx_rate_limit_error(self, mock_anthropic_class: Mock) -> None:
        """Test handling of rate limit errors."""
        import anthropic

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limit exceeded",
            response=Mock(status_code=429),
            body={"error": {"message": "Rate limit exceeded"}},
        )

        client = AnthropicClient(api_key=self.api_key)
        license_text = "Some license text"

        with pytest.raises(anthropic.RateLimitError):
            client.convert_to_spdx(license_text)

        mock_client.messages.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_convert_to_spdx_authentication_error(
        self, mock_anthropic_class: Mock
    ) -> None:
        """Test handling of authentication errors (invalid API key)."""
        import anthropic

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = anthropic.AuthenticationError(
            message="Invalid API key",
            response=Mock(status_code=401),
            body={"error": {"message": "Invalid API key"}},
        )

        client = AnthropicClient(api_key=self.api_key)
        license_text = "Some license text"

        with pytest.raises(anthropic.AuthenticationError):
            client.convert_to_spdx(license_text)

        mock_client.messages.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_convert_to_spdx_connection_error(self, mock_anthropic_class: Mock) -> None:
        """Test handling of connection errors."""
        import anthropic

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = anthropic.APIConnectionError(
            request=Mock()
        )

        client = AnthropicClient(api_key=self.api_key)
        license_text = "Some license text"

        with pytest.raises(anthropic.APIConnectionError):
            client.convert_to_spdx(license_text)

        mock_client.messages.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_convert_to_spdx_not_found_error(self, mock_anthropic_class: Mock) -> None:
        """Test handling of NotFoundError for non-existent models."""
        import anthropic

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client
        # Anthropic returns 404 NotFoundError for invalid/non-existent models
        mock_client.messages.create.side_effect = anthropic.NotFoundError(
            message="model: invalid-model-xyz",
            response=Mock(status_code=404),
            body={
                "type": "error",
                "error": {
                    "type": "not_found_error",
                    "message": "model: invalid-model-xyz",
                },
            },
        )

        client = AnthropicClient(api_key=self.api_key)
        license_text = "Some license text"

        with pytest.raises(anthropic.NotFoundError):
            client.convert_to_spdx(license_text)

        mock_client.messages.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_convert_to_spdx_context_length_exceeded_returns_unknown(
        self, mock_anthropic_class: Mock
    ) -> None:
        """Test that context length exceeded errors return UNKNOWN instead of raising."""
        import anthropic

        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        # Create a context length exceeded error (Anthropic format)
        error_body = {
            "error": {
                "type": "invalid_request_error",
                "message": "prompt: maximum context length is 100000 tokens, but your messages resulted in 120000 tokens",
            }
        }
        mock_client.messages.create.side_effect = anthropic.APIStatusError(
            message="Bad Request",
            response=Mock(status_code=400),
            body=error_body,
        )

        client = AnthropicClient(api_key=self.api_key)
        license_text = "Very long license text that exceeds context length..."

        # Should return UNKNOWN instead of raising
        result = client.convert_to_spdx(license_text)
        assert result == "UNKNOWN"

        mock_client.messages.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_convert_to_spdx_composite_license_expression(
        self, mock_anthropic_class: Mock
    ) -> None:
        """Test successful conversion to composite SPDX license expression."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        mock_response = Mock()
        mock_content = Mock()
        mock_content.text = "MIT OR Apache-2.0"
        mock_response.content = [mock_content]
        mock_client.messages.create.return_value = mock_response

        client = AnthropicClient(api_key=self.api_key)
        license_text = "Dual licensed under MIT or Apache 2.0"

        result = client.convert_to_spdx(license_text)

        assert result == "MIT OR Apache-2.0"
        mock_client.messages.create.assert_called_once()

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_convert_to_spdx_license_with_exception(
        self, mock_anthropic_class: Mock
    ) -> None:
        """Test successful conversion to SPDX license expression with exception."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        mock_response = Mock()
        mock_content = Mock()
        mock_content.text = "GPL-2.0-only WITH Classpath-exception-2.0"
        mock_response.content = [mock_content]
        mock_client.messages.create.return_value = mock_response

        client = AnthropicClient(api_key=self.api_key)
        license_text = "GPL 2.0 with Classpath exception"

        result = client.convert_to_spdx(license_text)

        assert result == "GPL-2.0-only WITH Classpath-exception-2.0"
        mock_client.messages.create.assert_called_once()


class TestCreateLLMClient:
    """Test LLM client factory function."""

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_create_openai_client_default_model(self, mock_openai_class: Mock) -> None:
        """Test creating OpenAI client with default model."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        client = create_llm_client("openai", "test-key")

        assert isinstance(client, OpenAIClient)
        assert client.model == "gpt-4"
        mock_openai_class.assert_called_once_with(api_key="test-key")

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_create_openai_client_custom_model(self, mock_openai_class: Mock) -> None:
        """Test creating OpenAI client with custom model."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        client = create_llm_client("openai", "test-key", "gpt-3.5-turbo")

        assert isinstance(client, OpenAIClient)
        assert client.model == "gpt-3.5-turbo"

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_create_anthropic_client_default_model(
        self, mock_anthropic_class: Mock
    ) -> None:
        """Test creating Anthropic client with default model."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        client = create_llm_client("anthropic", "test-key")

        assert isinstance(client, AnthropicClient)
        assert client.model == "claude-3-7-sonnet-20250219"
        mock_anthropic_class.assert_called_once_with(api_key="test-key")

    @patch("dd_license_attribution.license_cleaner.llm_client.anthropic.Anthropic")
    def test_create_anthropic_client_custom_model(
        self, mock_anthropic_class: Mock
    ) -> None:
        """Test creating Anthropic client with custom model."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        client = create_llm_client("anthropic", "test-key", "claude-3-opus-20240229")

        assert isinstance(client, AnthropicClient)
        assert client.model == "claude-3-opus-20240229"
        mock_anthropic_class.assert_called_once_with(api_key="test-key")

    def test_create_client_unsupported_provider(self) -> None:
        """Test error handling for unsupported provider."""
        with pytest.raises(
            ValueError,
            match="Unsupported LLM provider: unsupported. Supported providers: openai, anthropic",
        ):
            create_llm_client("unsupported", "test-key")

    @patch("dd_license_attribution.license_cleaner.llm_client.openai.OpenAI")
    def test_create_client_case_insensitive(self, mock_openai_class: Mock) -> None:
        """Test that provider name is case insensitive."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        client1 = create_llm_client("OpenAI", "test-key")
        client2 = create_llm_client("OPENAI", "test-key")

        assert isinstance(client1, OpenAIClient)
        assert isinstance(client2, OpenAIClient)

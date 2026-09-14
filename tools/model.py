"""Model configuration, in one place.

Two providers, chosen with GRUTTO_MODEL_PROVIDER:

  bedrock    Claude on Amazon Bedrock. The default, and what the hackathon's
             AWS credits cover. Needs AWS credentials and a verified account.
  anthropic  Claude via the Anthropic API directly. Needs ANTHROPIC_API_KEY.

Both run the same agents. Nothing else in the codebase knows or cares which
one is in use.
"""

import os

DEFAULT_BEDROCK = "global.anthropic.claude-sonnet-4-6"
DEFAULT_ANTHROPIC = "claude-sonnet-4-6"


def build_model():
    provider = os.environ.get("GRUTTO_MODEL_PROVIDER", "bedrock").lower()

    if provider == "bedrock":
        from strands.models import BedrockModel

        return BedrockModel(
            model_id=os.environ.get("GRUTTO_MODEL_ID", DEFAULT_BEDROCK),
            temperature=0.3,
        )

    if provider == "anthropic":
        from strands.models.anthropic import AnthropicModel

        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "GRUTTO_MODEL_PROVIDER=anthropic needs ANTHROPIC_API_KEY in .env"
            )
        return AnthropicModel(
            client_args={"api_key": key},
            model_id=os.environ.get("GRUTTO_MODEL_ID", DEFAULT_ANTHROPIC),
            max_tokens=4096,
            params={"temperature": 0.3},
        )

    raise ValueError(
        f"Unknown GRUTTO_MODEL_PROVIDER: {provider!r}. Use 'bedrock' or 'anthropic'."
    )

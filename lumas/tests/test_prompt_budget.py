from lumas.backend.prompting.builder import PromptBuilder


def test_chat_prompt_is_compacted_for_2048_context():
    builder = PromptBuilder()
    messages = builder.build_chat_messages(
        query="Explain the important lessons and likely exam topics. " * 40,
        context_chunks=["Long document section about geography. " * 1000] * 5,
        history=[
            {"role": "user", "content": "previous question " * 500},
            {"role": "assistant", "content": "previous answer " * 500},
        ],
    )

    # 512 tokens remain available for the model response.
    assert builder.estimate_message_tokens(messages) <= 1536
    assert messages[-1]["role"] == "user"
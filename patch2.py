import pathlib

path = pathlib.Path('shopee_core/chatbot_service.py')
content = path.read_text(encoding='utf-8')

old_sig = '''def run_chatbot_turn(
    user_message: str,
    segmento: str,
    chat_history: list[dict[str, str]] | None = None,
    full_context: str = \"\",
    attachments: list | None = None,
    attachment_types: list[str] | None = None,
    **kwargs: Any,
) -> dict:'''

new_sig = '''def run_chatbot_turn(
    user_message: str,
    segmento: str,
    chat_history: list[dict[str, str]] | None = None,
    full_context: str = \"\",
    attachments: list | None = None,
    attachment_types: list[str] | None = None,
    channel: str = \"desktop\",
    **kwargs: Any,
) -> dict:'''

content = content.replace(old_sig, new_sig)

old_call = '''    result = process_chat_turn(
        user_message=user_message,
        attachments=attachments or [],
        attachment_types=attachment_types or [],
        chat_history=chat_history or [],
        full_context=full_context,
        segmento=segmento,
        **kwargs,
    )'''

new_call = '''    result = process_chat_turn(
        user_message=user_message,
        attachments=attachments or [],
        attachment_types=attachment_types or [],
        chat_history=chat_history or [],
        full_context=full_context,
        segmento=segmento,
        channel=channel,
        **kwargs,
    )'''

content = content.replace(old_call, new_call)
path.write_text(content, encoding='utf-8')
print("Patched chatbot_service.py")

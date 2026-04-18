import re

import_list = (
    "salvar_ou_baixar, resolve_shopee_url, fetch_shop_info, fetch_shop_products_intercept, "
    "fetch_competitors_intercept, fetch_reviews_intercept, generate_full_optimization, "
    "build_catalog_context, chat_with_gemini, analyze_reviews_with_gemini, "
    "generate_ai_scenario, generate_gradient_background, apply_contact_shadow, "
    "improve_image_quality, upscale_image, MODELOS_VISION, client, "
    "build_full_chat_context, detect_chat_intent, analyze_product_image_vision, "
    "process_chat_turn, suggest_faq_from_history, MODELOS_TEXTO, get_client"
)

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

target_funcs = [
    'render_auditoria', '_render_canvas_area', 'render_chatbot', 
    'render_sentinela', '_render_quick_actions', '_send_message',
    '_gerar_faq', '_render_faq_output', '_render_post_response_actions'
]

for func in target_funcs:
    pattern = re.compile(r'(^[ \t]*def ' + func + r'\b.*?:\s*\n)', re.MULTILINE | re.DOTALL)
    
    def repl(match):
        orig_def = match.group(1)
        indent_match = re.match(r'^([ \t]*)', orig_def)
        indent = indent_match.group(1) if indent_match else ''
        inner_indent = indent + '    '
        
        lazy_code = (
            f'{inner_indent}from backend_core import (\n'
            f'{inner_indent}    {import_list}\n'
            f'{inner_indent})\n'
            f'{inner_indent}from PIL import Image\n'
        )
        return orig_def + lazy_code

    text = pattern.sub(repl, text, count=1)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)

print('Inject Completed')

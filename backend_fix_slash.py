with open('backend_core.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Substitui as duas contra-barras seguidas das aspas para apenas uma contra-barra n
text = text.replace('\\\\n', '\\n')

with open('backend_core.py', 'w', encoding='utf-8') as f:
    f.write(text)

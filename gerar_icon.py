from PIL import Image
from rembg import remove
import io
import os

# 1. Carrega a imagem original
with open("icon_original.png", "rb") as f:
    input_data = f.read()

# 2. IA remove apenas o fundo (preservando o branco interno do ícone)
print("✂️ Removendo fundo do ícone via IA...")
output_data = remove(input_data)
img = Image.open(io.BytesIO(output_data)).convert("RGBA")

# 3. Define os tamanhos padrão do Windows
tamanhos = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

if not os.path.exists("assets"):
    os.makedirs("assets")

# 4. Salva as versões com transparência real
img.save("assets/icon.png")
img.save("assets/icon.ico", format="ICO", sizes=tamanhos)
print("✅ icon.ico gerado com transparência inteligente em assets/")

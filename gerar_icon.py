from PIL import Image
import os

# 1. Abre a imagem original
img = Image.open("icon_original.png")

# 2. Converte para RGBA (Garante canal de transparência)
img = img.convert("RGBA")

# Garante a limpeza do canal RGBA, removendo fundos indesejados caso seja RGB
data = img.getdata()
# Se houver branco chapado ao redor (RGB alto) converte para transparente
# Como precaução, verifica a cor do pixel. O ícone da Shopee possui borda branca arredondada,
# se o objetivo é bordas redondas transparentes, talvez o fundo (0,0,0) estava sem mascara let's just use RGBA.
# Se o fundo fosse preto não transparente mas RGB:
new_data = []
for d in data:
    # d é (R, G, B, A). Removendo branco puro
    if d[0] > 240 and d[1] > 240 and d[2] > 240:
        new_data.append((255, 255, 255, 0))
    # Removendo fundo 'preto' puro / cor sólida de "vazio" sem errar a arte viva
    elif d[0] < 10 and d[1] < 10 and d[2] < 10:
        new_data.append((255, 255, 255, 0))
    else:
        new_data.append(d)

img.putdata(new_data)

# 3. Define os tamanhos padrão do Windows
tamanhos = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# 4. Salva o ICO garantindo que o canal Alpha seja preservado
# O formato ICO no Pillow suporta transparência nativamente se a imagem for RGBA
if not os.path.exists("assets"):
    os.makedirs("assets")

img.save("assets/icon.ico", format="ICO", sizes=tamanhos, bitmap_format="png")
img.save("assets/icon.png", format="PNG") # Atualiza o icon.png tbm
print("✅ Ícone V2.0.0 gerado com transparência real!")

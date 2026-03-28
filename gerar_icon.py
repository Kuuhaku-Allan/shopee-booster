from PIL import Image

# Carrega a imagem que você baixou (Ícone 4)
img = Image.open("icon_original.png")

# Define os tamanhos padrão para um ícone de Windows completo
tamanhos = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# Salva como PNG (melhor para o ícone da bandeja com transparência)
img.save("assets/icon.png")

# Salva como .ico contendo todas as resoluções
img.save("assets/icon.ico", format="ICO", sizes=tamanhos)
print("✅ icon.png e icon.ico gerados com sucesso em assets/")

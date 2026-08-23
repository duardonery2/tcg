import os
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI

# 1. Configuração da API (Insira sua chave da OpenAI)
client = OpenAI(api_key="SUA_CHAVE_API_AQUI")

# 2. Dicionário de Cores baseado nas suas regras
CORES_FUNDO = {
    "Herói": "#30004a",       # Roxo Profundo
    "Monstro": "#30004a",     # Roxo Profundo
    "Maldição": "#800080",    # Roxo Vibrante
    "Encantamento": "#d3d3d3",# Cinza Claro
    "Domínio Fogo": "#ff4500",
    "Domínio Água": "#1e90ff",
    "Domínio Terra": "#228b22",
    "Domínio Vento": "#f5f5f5"
}

def gerar_arte_ia(nome, tipo, elemento):
    """Gera a imagem usando DALL-E 3 com um prompt otimizado."""
    prompt = (
        f"A masterpiece fantasy trading card game illustration of {nome}. "
        f"Concept: {tipo} of the {elemento} element. "
        "Style: Dark fantasy, highly detailed, digital painting, dramatic lighting, "
        "no text, centered composition."
    )
    
    print(f"Gerando arte para: {nome}...")
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    
    url_imagem = response.data[0].url
    resposta_http = requests.get(url_imagem)
    img = Image.open(BytesIO(resposta_http.content))
    return img.resize((600, 600)) # Redimensiona para caber na carta

def montar_carta(dados_carta):
    """Cria o template visual e insere os textos e a arte gerada."""
    # Define a cor de fundo com base no tipo/elemento
    chave_cor = dados_carta['Tipo']
    if dados_carta['Tipo'] == 'Domínio':
        chave_cor = f"Domínio {dados_carta['Elemento']}"
    
    cor = CORES_FUNDO.get(chave_cor, "#ffffff")
    
    # Cria a tela base da carta (tamanho padrão Poker Size escalado)
    carta = Image.new('RGB', (750, 1050), color=cor)
    draw = ImageDraw.Draw(carta)
    
    # Fontes (Você precisa ter arquivos .ttf na mesma pasta ou usar as padrões do sistema)
    # Exemplo: font_titulo = ImageFont.truetype("arial.ttf", 40)
    font_titulo = ImageFont.load_default(size=40)
    font_texto = ImageFont.load_default(size=25)
    
    # Gerar e colar a arte no centro
    #arte = gerar_arte_ia(dados_carta['Nome'], dados_carta['Tipo'], dados_carta['Elemento'])
    #carta.paste(arte, (75, 120)) # Posiciona a imagem
    
    # Desenhar Textos Básicos
    # Título
    draw.text((75, 50), dados_carta['Nome'].upper(), fill="white" if cor != "#d3d3d3" else "black", font=font_titulo)
    # Custo de Mana (canto superior direito)
    draw.text((650, 50), f"Cost: {dados_carta['Custo de Mana']}", fill="yellow", font=font_titulo)
    
    # Caixa de Texto da Habilidade
    draw.rectangle([75, 750, 675, 900], fill="#222222") # Fundo da caixa de texto
    draw.text((90, 770), dados_carta['Efeito / Habilidade'], fill="white", font=font_texto)
    
    # Atributos (Apenas para Heróis e Monstros)
    if dados_carta['Tipo'] in ['Herói', 'Monstro']:
        status = f"DEF: {dados_carta['Resistência']}   |   ATK: {dados_carta['Combate']}"
        draw.text((75, 950), status, fill="white", font=font_titulo)
        
    # Salva a imagem final
    nome_arquivo = f"{dados_carta['Nome'].replace(' ', '_')}.png"
    carta.save(nome_arquivo)
    print(f"Carta salva como {nome_arquivo}!\n")

# --- Exemplo de Execução ---
# Na prática, você usaria o pandas para ler a planilha que criamos:
# import pandas as pd
# df = pd.read_csv('Cartas do Jogo de Duelo de Feiticeiros - Cartas do Jogo de Duelo de Feiticeiros.csv')
# for _, linha in df.iterrows():
#     montar_carta(linha.to_dict())

# Exemplo de teste com uma carta:
carta_teste = {
    "Nome": "Rei Arthur",
    "Tipo": "Herói",
    "Elemento": "Fogo",
    "Custo de Mana": "3",
    "Resistência": "16",
    "Combate": "18",
    "Efeito / Habilidade": "Excalibur: Ganha +4 de Combate neste turno."
}

# Descomente a linha abaixo para testar quando tiver sua chave da OpenAI
montar_carta(carta_teste)

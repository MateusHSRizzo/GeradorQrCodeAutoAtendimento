# ==============================
# BIBLIOTECAS
# ==============================
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import base64
import qrcode
import re
import io
import zipfile
import os # Adicionado para interagir com o sistema de ficheiros

# ==============================
# CONFIGURAÇÃO DA PÁGINA
# ==============================
st.set_page_config(page_title="Gerador de Comandas")

# ==============================
# FUNÇÕES AUXILIARES
# ==============================

# ESTA É A FUNÇÃO EXATA DO SEU SCRIPT COLAB FUNCIONAL
def aplicar_mascara(documento, tipo):
    numeros = re.sub(r'\D', '', documento)
    if tipo == 'CPF' and len(numeros) > 0:
        numeros = numeros[:11]
        mascara = '{}.{}.{}-{}'.format(numeros[0:3], numeros[3:6], numeros[6:9], numeros[9:11]) if len(numeros) == 11 else numeros
    elif tipo == 'CNPJ' and len(numeros) > 0:
        numeros = numeros[:14]
        mascara = '{}.{}.{}/{}-{}'.format(numeros[0:2], numeros[2:5], numeros[5:8], numeros[8:12], numeros[12:14]) if len(numeros) == 14 else numeros
    else:
        mascara = numeros
    return mascara + ':'

# ESTA É A FUNÇÃO EXATA DO SEU SCRIPT COLAB FUNCIONAL
def gerar_qrcode(numero, dado_base, tamanho, rotacao_qr):
    texto_original = f"{dado_base}{numero}"
    base64_encoded = base64.b64encode(texto_original.encode()).decode()
    url = f"https://pediucomeu.com.br/autoatendimento/{base64_encoded}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    img_qr = img_qr.resize((tamanho, tamanho), Image.Resampling.NEAREST)
    if rotacao_qr != 0:
        img_qr = img_qr.rotate(rotacao_qr, expand=True)
    return img_qr

# ==================================================================
# ALTERAÇÃO: Nova função para ler as fontes da pasta 'fonts'
# ==================================================================
@st.cache_data # Usar cache para não ler os ficheiros repetidamente
def carregar_fontes_disponiveis(pasta_fontes="fonts"):
    """
    Verifica uma pasta, lê os ficheiros .ttf e retorna um dicionário
    mapeando o nome real da fonte para o seu caminho.
    """
    fontes = {}
    if not os.path.isdir(pasta_fontes):
        return fontes # Retorna dicionário vazio se a pasta não existir

    for nome_ficheiro in os.listdir(pasta_fontes):
        if nome_ficheiro.lower().endswith('.ttf'):
            caminho_completo = os.path.join(pasta_fontes, nome_ficheiro)
            try:
                # Abre o ficheiro de fonte para extrair o seu nome real
                font = ImageFont.truetype(caminho_completo, size=10)
                # O nome geralmente é uma tupla (Nome da Família, Estilo)
                nome_real = " ".join(font.getname())
                fontes[nome_real] = caminho_completo
            except Exception:
                # Se não conseguir ler o nome, usa o nome do ficheiro como fallback
                nome_fallback = os.path.splitext(nome_ficheiro)[0]
                fontes[nome_fallback] = caminho_completo
    return fontes
# ==================================================================
# FIM DA ALTERAÇÃO
# ==================================================================

def carregar_fonte(caminho_fonte, tamanho):
    """Carrega a fonte a partir de um caminho de ficheiro local."""
    try:
        return ImageFont.truetype(caminho_fonte, tamanho)
    except FileNotFoundError:
        st.error(f"Erro: O ficheiro da fonte '{caminho_fonte}' não foi encontrado. Verifique se a pasta 'fonts' e os ficheiros .ttf estão no seu repositório.")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro ao carregar a fonte: {e}")
        return None

def gerar_imagem_comanda(background, numero, dado_base, config):
    """Cria uma comanda sobrepondo QR Code e texto na imagem de fundo."""
    imagem_final = background.copy().convert("RGBA")
    draw = ImageDraw.Draw(imagem_final)

    img_qr = gerar_qrcode(numero, dado_base, config['tamanho_qr'], config['rotacao_qr'])
    qr_w, qr_h = img_qr.size
    pos_qr = (config['qr_x'] - qr_w // 2, config['qr_y'] - qr_h // 2)
    imagem_final.paste(img_qr, pos_qr, img_qr)

    fonte = carregar_fonte(config['caminho_fonte'], config['tamanho_texto'])
    if fonte is None:
        return None
        
    texto_str = str(numero)
    
    texto_bbox = draw.textbbox((0, 0), texto_str, font=fonte)
    texto_w = texto_bbox[2] - texto_bbox[0]
    texto_h = texto_bbox[3] - texto_bbox[1]
    
    if config['rotacao_texto'] == 0:
        pos_texto = (config['texto_x'] - texto_w // 2, config['texto_y'] - texto_h // 2)
        draw.text(pos_texto, texto_str, font=fonte, fill=config['cor_texto'])
    else:
        texto_img = Image.new('RGBA', (texto_w, texto_h), (0, 0, 0, 0))
        draw_texto_temp = ImageDraw.Draw(texto_img)
        draw_texto_temp.text((-texto_bbox[0], -texto_bbox[1]), texto_str, font=fonte, fill=config['cor_texto'])
        
        texto_rotacionado = texto_img.rotate(config['rotacao_texto'], expand=True, fillcolor=(0,0,0,0))
        
        rot_w, rot_h = texto_rotacionado.size
        pos_rot = (config['texto_x'] - rot_w // 2, config['texto_y'] - rot_h // 2)
        imagem_final.paste(texto_rotacionado, pos_rot, texto_rotacionado)

    return imagem_final.convert("RGB")

# ==============================
# INICIALIZAÇÃO DO ESTADO DA SESSÃO
# ==============================
if 'imagens_geradas' not in st.session_state:
    st.session_state['imagens_geradas'] = None

# ==============================
# INTERFACE PRINCIPAL
# ==============================
st.title("📄 Gerador de Comandas com QR Code")
st.markdown("Configure as opções na barra lateral e clique em 'Gerar Prévias' para visualizar.")

# Carrega as fontes da pasta 'fonts'
fontes_disponiveis = carregar_fontes_disponiveis()

with st.sidebar:
    st.header("⚙️ Configurações")

    st.subheader("1. Ficheiros e Fonte")
    imagem_base_up = st.file_uploader(
        "1. Template Vazio da Comanda", 
        type=["png", "jpg", "jpeg"]
    )
    
    # ALTERAÇÃO: O menu de seleção agora é preenchido dinamicamente
    if fontes_disponiveis:
        fonte_selecionada = st.selectbox("2. Escolha a Fonte para os Números", options=sorted(fontes_disponiveis.keys()))
    else:
        st.error("A pasta 'fonts' não foi encontrada ou está vazia. Por favor, crie a pasta e adicione ficheiros .ttf.")
        fonte_selecionada = None # Desativa a seleção se não houver fontes

    st.subheader("2. Dados da Comanda")
    col1, col2 = st.columns(2)
    with col1:
        inicio = st.number_input("Número Inicial", value=1, step=1, min_value=1)
    with col2:
        fim = st.number_input("Número Final", value=10, step=1, min_value=inicio)
    
    tipo_doc = st.selectbox("Tipo de Documento", ["CNPJ", "CPF"])
    documento = st.text_input("Documento", placeholder="Digite apenas os números")

    if documento:
        st.subheader("🔗 Pré-visualização do Link")
        dado_base_para_url = aplicar_mascara(documento, tipo_doc)
        texto_exemplo = f"{dado_base_para_url}{inicio}"
        base64_exemplo = base64.b64encode(texto_exemplo.encode()).decode()
        url_exemplo = f"https://pediucomeu.com.br/autoatendimento/{base64_exemplo}"
        st.markdown(f"**Link da comanda `{inicio}`:**")
        st.code(url_exemplo, language=None)

    st.subheader("3. Layout e Posições")
    max_width, max_height = 2000, 2000 
    if imagem_base_up:
        imagem_base_up.seek(0)
        img_temp = Image.open(imagem_base_up)
        max_width, max_height = img_temp.size
        st.info(f"Dimensões da Imagem: {max_width}x{max_height} px")
    else:
        st.warning("Envie uma imagem para ajustar as posições com precisão.")

    tamanho_qr = st.slider("Tamanho do QR Code", 50, max_width, 450, 10)
    tamanho_texto = st.slider("Tamanho do Número", 10, int(max_height / 2), 150, 5)
    cor_texto = st.color_picker("Cor do Número", "#000000")
    
    qr_x = st.slider("Posição X do QR Code (Centro)", 0, max_width, 540, 5)
    qr_y = st.slider("Posição Y do QR Code (Centro)", 0, max_height, 1035, 5)
    texto_x = st.slider("Posição X do Número (Centro)", 0, max_width, 533, 5)
    texto_y = st.slider("Posição Y do Número (Centro)", 0, max_height, 1445, 5)

    st.subheader("4. Rotação")
    rotacao_qr = st.selectbox("Rotação do QR Code (°)", [0, 90, 180, 270], key="rot_qr")
    rotacao_texto = st.selectbox("Rotação do Número (°)", [0, 90, 180, 270], key="rot_texto")

# --- ÁREA DE PRÉ-VISUALIZAÇÃO ---
st.header("🖼️ Pré-visualização")

col_btn_1, col_btn_2 = st.columns(2)
with col_btn_1:
    if st.button("Gerar Prévias", type="primary", use_container_width=True):
        erros = []
        if not imagem_base_up: erros.append("o template vazio da comanda")
        if not documento.strip(): erros.append("o documento")
        if not fonte_selecionada: erros.append("uma fonte (verifique a pasta 'fonts')")

        if erros:
            msg_erro = " e ".join(filter(None, [", ".join(erros[:-1]), erros[-1]]))
            st.error(f"❌ Por favor, forneça {msg_erro} para continuar.")
            st.session_state['imagens_geradas'] = None
        else:
            with st.spinner(f"A gerar {fim - inicio + 1} comandas..."):
                imagem_base_up.seek(0)
                background = Image.open(imagem_base_up)
                
                dado_base_para_url = aplicar_mascara(documento, tipo_doc)
                
                config = {
                    'tamanho_qr': tamanho_qr, 'qr_x': qr_x, 'qr_y': qr_y,
                    'tamanho_texto': tamanho_texto, 'texto_x': texto_x, 'texto_y': texto_y,
                    'cor_texto': cor_texto,
                    'rotacao_qr': rotacao_qr, 'rotacao_texto': rotacao_texto,
                    'caminho_fonte': fontes_disponiveis[fonte_selecionada]
                }

                lista_imagens = []
                for numero in range(inicio, fim + 1):
                    img_gerada = gerar_imagem_comanda(background, numero, dado_base_para_url, config)
                    if img_gerada:
                        lista_imagens.append(img_gerada)
                
                st.session_state['imagens_geradas'] = lista_imagens
                if lista_imagens:
                    st.success(f"{len(lista_imagens)} comandas geradas com sucesso!")

with col_btn_2:
    if st.button("Limpar Prévias e Recomeçar", use_container_width=True):
        st.session_state['imagens_geradas'] = None
        st.rerun()

if st.session_state.get('imagens_geradas'):
    st.markdown("---")
    
    imagens_para_pdf = st.session_state['imagens_geradas']
    if imagens_para_pdf:
        pdf_bytes = io.BytesIO()
        imagens_para_pdf[0].save(pdf_bytes, format="PDF", save_all=True, append_images=imagens_para_pdf[1:])
        pdf_bytes.seek(0)
        
        st.download_button(
            "⬇️ Baixar PDF com Todas as Comandas",
            data=pdf_bytes,
            file_name=f"comandas_{inicio}_a_{fim}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            pdf_filename = f"comandas_{inicio}_a_{fim}.pdf"
            zip_file.writestr(pdf_filename, pdf_bytes.getvalue())
        
        zip_buffer.seek(0)

        st.download_button(
            label="⬇️ Baixar PDF Compactado (.zip)",
            data=zip_buffer,
            file_name=f"comandas_{inicio}_a_{fim}.zip",
            mime="application/zip",
            use_container_width=True
        )
        
        st.markdown("---")

        for i, img in enumerate(imagens_para_pdf):
            numero_atual = inicio + i
            st.image(img, caption=f"Prévia da Comanda Nº {numero_atual}", width=600)

elif imagem_base_up:
    imagem_base_up.seek(0)
    st.image(imagem_base_up, caption="O seu template. Escolha uma fonte e preencha os dados para continuar.", width=600)
else:
    st.info("A pré-visualização das suas comandas aparecerá aqui.")

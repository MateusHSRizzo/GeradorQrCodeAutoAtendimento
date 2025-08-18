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
import os
from barcode import Code39
from barcode.writer import ImageWriter

# ==============================
# CONFIGURAÇÃO DA PÁGINA
# ==============================
st.set_page_config(page_title="Gerador de Comandas")

# ==============================
# FUNÇÕES GERAIS E DE FONTES
# ==============================

@st.cache_data
def carregar_fontes_disponiveis(pasta_fontes="fonts"):
    """
    Verifica uma pasta, lê os ficheiros .ttf e retorna um dicionário
    mapeando o nome real da fonte para o seu caminho.
    """
    fontes = {}
    if not os.path.isdir(pasta_fontes):
        return fontes

    for nome_ficheiro in os.listdir(pasta_fontes):
        if nome_ficheiro.lower().endswith('.ttf'):
            caminho_completo = os.path.join(pasta_fontes, nome_ficheiro)
            try:
                font = ImageFont.truetype(caminho_completo, size=10)
                nome_real = " ".join(font.getname())
                fontes[nome_real] = caminho_completo
            except Exception:
                nome_fallback = os.path.splitext(nome_ficheiro)[0]
                fontes[nome_fallback] = caminho_completo
    return fontes

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

# ===================================================================
# SEÇÃO 1: LÓGICA DO GERADOR DE QR CODE
# ===================================================================

def aplicar_mascara_qrcode(documento, tipo):
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

def gerar_qrcode(numero, dado_base, tamanho, rotacao_qr):
    texto_original = f"{dado_base}{numero}"
    base64_encoded = base64.b64encode(texto_original.encode()).decode()
    url = f"https://pediucomeu.com.br/autoatendimento/{base64_encoded}"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    img_qr = img_qr.resize((tamanho, tamanho), Image.Resampling.NEAREST)
    if rotacao_qr != 0:
        img_qr = img_qr.rotate(rotacao_qr, expand=True)
    return img_qr

def gerar_imagem_qrcode(background, numero, dado_base, config):
    imagem_final = background.copy().convert("RGBA")
    draw = ImageDraw.Draw(imagem_final)
    img_qr = gerar_qrcode(numero, dado_base, config['tamanho_qr'], config['rotacao_qr'])
    qr_w, qr_h = img_qr.size
    pos_qr = (config['qr_x'] - qr_w // 2, config['qr_y'] - qr_h // 2)
    imagem_final.paste(img_qr, pos_qr, img_qr)
    fonte = carregar_fonte(config['caminho_fonte'], config['tamanho_texto'])
    if fonte is None: return None
    texto_str = str(numero)
    texto_bbox = draw.textbbox((0, 0), texto_str, font=fonte)
    texto_w, texto_h = texto_bbox[2] - texto_bbox[0], texto_bbox[3] - texto_bbox[1]
    if config['rotacao_texto'] == 0:
        pos_texto = (config['texto_x'] - texto_w // 2, config['texto_y'] - texto_h // 2)
        draw.text(pos_texto, texto_str, font=fonte, fill=config['cor_texto'])
    else:
        texto_img = Image.new('RGBA', (texto_w, texto_h), (0,0,0,0))
        draw_texto_temp = ImageDraw.Draw(texto_img)
        draw_texto_temp.text((-texto_bbox[0], -texto_bbox[1]), texto_str, font=fonte, fill=config['cor_texto'])
        texto_rotacionado = texto_img.rotate(config['rotacao_texto'], expand=True, fillcolor=(0,0,0,0))
        rot_w, rot_h = texto_rotacionado.size
        pos_rot = (config['texto_x'] - rot_w // 2, config['texto_y'] - rot_h // 2)
        imagem_final.paste(texto_rotacionado, pos_rot, texto_rotacionado)
    return imagem_final.convert("RGB")

# ===================================================================
# SEÇÃO 2: LÓGICA DO GERADOR DE CÓDIGO DE BARRAS
# ===================================================================

def gerar_code39(numero, prefixo, largura, altura, corte_vertical, rotacao_barra, corte_esq, corte_dir):
    codigo = f"{prefixo}{str(numero).zfill(4)}"
    writer = ImageWriter()
    writer.set_options({'module_width': 0.7, 'module_height': altura / 10, 'quiet_zone': 2.0, 'font_size': 0, 'text_distance': 0, 'write_text': False})
    barcode_obj = Code39(codigo, writer=writer, add_checksum=False)
    output = io.BytesIO()
    barcode_obj.write(output)
    output.seek(0)
    imagem = Image.open(output)
    largura_real, altura_real = imagem.size
    corte_altura = int(altura_real * (1 - (corte_vertical / 100)))
    corte_esq_px = int(largura_real * (corte_esq / 100))
    corte_dir_px = int(largura_real * (1 - (corte_dir / 100)))
    imagem_cortada = imagem.crop((corte_esq_px, 0, corte_dir_px, corte_altura))
    imagem_redimensionada = imagem_cortada.resize((largura, altura), Image.Resampling.NEAREST)
    if rotacao_barra != 0:
        imagem_redimensionada = imagem_redimensionada.rotate(rotacao_barra, expand=True)
    return imagem_redimensionada

def gerar_imagem_barcode(background, numero, config):
    imagem_final = background.copy().convert("RGBA")
    draw = ImageDraw.Draw(imagem_final)
    codigo_barras = gerar_code39(numero, config['prefixo'], config['largura'], config['altura'], config['corte_vertical'], config['rotacao_barra'], config['corte_esq'], config['corte_dir']).convert("RGBA")
    bar_w, bar_h = codigo_barras.size
    pos_bar = (config['bar_x'] - bar_w // 2, config['bar_y'] - bar_h // 2)
    imagem_final.paste(codigo_barras, pos_bar, codigo_barras)
    fonte = carregar_fonte(config['caminho_fonte'], config['tamanho_texto'])
    if fonte is None: return None
    texto_str = str(numero).zfill(4)
    texto_bbox = draw.textbbox((0, 0), texto_str, font=fonte)
    texto_w, texto_h = texto_bbox[2] - texto_bbox[0], texto_bbox[3] - texto_bbox[1]
    if config['rotacao_texto'] == 0:
        pos_texto = (config['texto_x'] - texto_w // 2, config['texto_y'] - texto_h // 2)
        draw.text(pos_texto, texto_str, font=fonte, fill=config['cor_texto'])
    else:
        texto_img = Image.new('RGBA', (texto_w, texto_h), (0,0,0,0))
        draw_texto_temp = ImageDraw.Draw(texto_img)
        draw_texto_temp.text((-texto_bbox[0], -texto_bbox[1]), texto_str, font=fonte, fill=config['cor_texto'])
        texto_rotacionado = texto_img.rotate(config['rotacao_texto'], expand=True, fillcolor=(0,0,0,0))
        rot_w, rot_h = texto_rotacionado.size
        pos_rot = (config['texto_x'] - rot_w // 2, config['texto_y'] - rot_h // 2)
        imagem_final.paste(texto_rotacionado, pos_rot, texto_rotacionado)
    return imagem_final.convert("RGB")

# ===================================================================
# INTERFACE PRINCIPAL
# ===================================================================

st.title("📄 Gerador de Comandas")

fontes_disponiveis = carregar_fontes_disponiveis()

modo = st.sidebar.radio("Escolha o tipo de código:", ("QR Code", "Código de Barras"))

st.sidebar.header("⚙️ Configurações")

if modo == "QR Code":
    st.sidebar.subheader("1. Ficheiros e Fonte")
    imagem_base_up = st.sidebar.file_uploader("1. Template Vazio da Comanda", type=["png", "jpg", "jpeg"], key="qr_uploader")
    if fontes_disponiveis:
        fonte_selecionada = st.sidebar.selectbox("2. Escolha a Fonte", options=sorted(fontes_disponiveis.keys()), key="qr_font_select")
    else:
        st.sidebar.error("A pasta 'fonts' está vazia.")
        fonte_selecionada = None

    st.sidebar.subheader("2. Dados da Comanda")
    col1, col2 = st.sidebar.columns(2)
    inicio = col1.number_input("Número Inicial", value=1, step=1, min_value=1, key="qr_inicio")
    fim = col2.number_input("Número Final", value=10, step=1, min_value=inicio, key="qr_fim")
    tipo_doc = st.sidebar.selectbox("Tipo de Documento", ["CNPJ", "CPF"], key="qr_tipo_doc")
    documento = st.sidebar.text_input("Documento", placeholder="Digite apenas os números", key="qr_doc")

    if documento:
        st.sidebar.subheader("🔗 Pré-visualização do Link")
        dado_base_para_url = aplicar_mascara_qrcode(documento, tipo_doc)
        texto_exemplo = f"{dado_base_para_url}{inicio}"
        base64_exemplo = base64.b64encode(texto_exemplo.encode()).decode()
        url_exemplo = f"https://pediucomeu.com.br/autoatendimento/{base64_exemplo}"
        st.sidebar.markdown(f"**Link da comanda `{inicio}`:**")
        st.sidebar.code(url_exemplo, language=None)

    st.sidebar.subheader("3. Layout e Posições")
    max_width, max_height = 2000, 2000
    if imagem_base_up:
        imagem_base_up.seek(0)
        img_temp = Image.open(imagem_base_up)
        max_width, max_height = img_temp.size
        st.sidebar.info(f"Dimensões: {max_width}x{max_height} px")
    
    tamanho_qr = st.sidebar.slider("Tamanho do QR Code", 50, max_width, 450, 10, key="qr_tam_qr")
    tamanho_texto_qr = st.sidebar.slider("Tamanho do Número", 10, int(max_height / 2), 150, 5, key="qr_tam_txt")
    cor_texto_qr = st.sidebar.color_picker("Cor do Número", "#000000", key="qr_cor")
    qr_x = st.sidebar.slider("Posição X do QR Code", 0, max_width, 540, 5, key="qr_x")
    qr_y = st.sidebar.slider("Posição Y do QR Code", 0, max_height, 1035, 5, key="qr_y")
    texto_x_qr = st.sidebar.slider("Posição X do Número", 0, max_width, 533, 5, key="qr_txt_x")
    texto_y_qr = st.sidebar.slider("Posição Y do Número", 0, max_height, 1445, 5, key="qr_txt_y")
    
    st.sidebar.subheader("4. Rotação")
    rotacao_qr = st.sidebar.selectbox("Rotação do QR Code (°)", [0, 90, 180, 270], key="qr_rot_qr")
    rotacao_texto_qr = st.sidebar.selectbox("Rotação do Número (°)", [0, 90, 180, 270], key="qr_rot_txt")

    st.header("🖼️ Pré-visualização (QR Code)")
    col_btn_1, col_btn_2 = st.columns(2)
    if col_btn_1.button("Gerar Prévias", type="primary", use_container_width=True, key="qr_gerar"):
        erros = []
        if not imagem_base_up: erros.append("o template")
        if not documento.strip(): erros.append("o documento")
        if not fonte_selecionada: erros.append("uma fonte")
        if erros:
            st.error(f"❌ Por favor, forneça {', '.join(erros)} para continuar.")
        else:
            with st.spinner("A gerar comandas..."):
                imagem_base_up.seek(0)
                background = Image.open(imagem_base_up)
                dado_base_para_url = aplicar_mascara_qrcode(documento, tipo_doc)
                config = {'tamanho_qr': tamanho_qr, 'qr_x': qr_x, 'qr_y': qr_y, 'tamanho_texto': tamanho_texto_qr, 'texto_x': texto_x_qr, 'texto_y': texto_y_qr, 'cor_texto': cor_texto_qr, 'rotacao_qr': rotacao_qr, 'rotacao_texto': rotacao_texto_qr, 'caminho_fonte': fontes_disponiveis[fonte_selecionada]}
                st.session_state['imagens_geradas'] = [img for numero in range(inicio, fim + 1) if (img := gerar_imagem_qrcode(background, numero, dado_base_para_url, config)) is not None]
                if st.session_state['imagens_geradas']:
                    st.success("Comandas geradas com sucesso!")

elif modo == "Código de Barras":
    st.sidebar.subheader("1. Ficheiros e Fonte")
    imagem_base_up = st.sidebar.file_uploader("1. Template Vazio da Comanda", type=["png", "jpg", "jpeg"], key="bc_uploader")
    if fontes_disponiveis:
        fonte_selecionada = st.sidebar.selectbox("2. Escolha a Fonte", options=sorted(fontes_disponiveis.keys()), key="bc_font_select")
    else:
        st.sidebar.error("A pasta 'fonts' está vazia.")
        fonte_selecionada = None

    st.sidebar.subheader("2. Dados da Comanda")
    col1, col2 = st.sidebar.columns(2)
    inicio = col1.number_input("Número Inicial", value=1, step=1, min_value=1, key="bc_inicio")
    fim = col2.number_input("Número Final", value=10, step=1, min_value=inicio, key="bc_fim")
    prefixo = st.sidebar.text_input("Prefixo (opcional)", "/", key="bc_prefixo")

    st.sidebar.subheader("3. Layout e Posições")
    max_width, max_height = 2000, 2000
    if imagem_base_up:
        imagem_base_up.seek(0)
        img_temp = Image.open(imagem_base_up)
        max_width, max_height = img_temp.size
        st.sidebar.info(f"Dimensões: {max_width}x{max_height} px")

    # ==================================================================
    # ALTERAÇÃO: Valores padrão atualizados conforme a imagem.
    # ==================================================================
    largura_barra = st.sidebar.slider("Largura da Barra", 100, max_width, 570, 10, key="bc_largura")
    altura_barra = st.sidebar.slider("Altura da Barra", 50, int(max_height / 2), 215, 5, key="bc_altura")
    tamanho_texto_bc = st.sidebar.slider("Tamanho do Número", 10, int(max_height / 2), 142, 2, key="bc_tam_txt")
    cor_texto_bc = st.sidebar.color_picker("Cor do Número", "#FFFFFF", key="bc_cor")
    bar_x = st.sidebar.slider("Posição X da Barra", 0, max_width, 535, 5, key="bc_x")
    bar_y = st.sidebar.slider("Posição Y da Barra", 0, max_height, 600, 5, key="bc_y")
    texto_x_bc = st.sidebar.slider("Posição X do Número", 0, max_width, 535, 5, key="bc_txt_x")
    texto_y_bc = st.sidebar.slider("Posição Y do Número", 0, max_height, 845, 5, key="bc_txt_y")
    # ==================================================================
    # FIM DA ALTERAÇÃO
    # ==================================================================

    st.sidebar.subheader("4. Cortes e Rotação")
    # ==================================================================
    # ALTERAÇÃO: Valores padrão atualizados conforme a imagem.
    # ==================================================================
    corte_vertical = st.sidebar.slider("Corte Vertical (%)", 0, 100, 27, 1, key="bc_corte_v")
    corte_esq = st.sidebar.slider("Corte Esquerdo (%)", 0, 40, 8, 1, key="bc_corte_e")
    corte_dir = st.sidebar.slider("Corte Direito (%)", 0, 40, 8, 1, key="bc_corte_d")
    # ==================================================================
    # FIM DA ALTERAÇÃO
    # ==================================================================
    rotacao_barra = st.sidebar.selectbox("Rotação da Barra (°)", [0, 90, 180, 270], key="bc_rot_bar")
    rotacao_texto_bc = st.sidebar.selectbox("Rotação do Número (°)", [0, 90, 180, 270], key="bc_rot_txt")

    st.header("🖼️ Pré-visualização (Código de Barras)")
    col_btn_1, col_btn_2 = st.columns(2)
    if col_btn_1.button("Gerar Prévias", type="primary", use_container_width=True, key="bc_gerar"):
        erros = []
        if not imagem_base_up: erros.append("o template")
        if not fonte_selecionada: erros.append("uma fonte")
        if erros:
            st.error(f"❌ Por favor, forneça {', '.join(erros)} para continuar.")
        else:
            with st.spinner("A gerar comandas..."):
                imagem_base_up.seek(0)
                background = Image.open(imagem_base_up)
                config = {'prefixo': prefixo, 'largura': largura_barra, 'altura': altura_barra, 'corte_vertical': corte_vertical, 'bar_x': bar_x, 'bar_y': bar_y, 'tamanho_texto': tamanho_texto_bc, 'texto_x': texto_x_bc, 'texto_y': texto_y_bc, 'cor_texto': cor_texto_bc, 'caminho_fonte': fontes_disponiveis[fonte_selecionada], 'rotacao_barra': rotacao_barra, 'rotacao_texto': rotacao_texto_bc, 'corte_esq': corte_esq, 'corte_dir': corte_dir}
                st.session_state['imagens_geradas'] = [img for numero in range(inicio, fim + 1) if (img := gerar_imagem_barcode(background, numero, config)) is not None]
                if st.session_state['imagens_geradas']:
                    st.success("Comandas geradas com sucesso!")

# --- ÁREA COMUM DE DOWNLOAD E EXIBIÇÃO ---
if 'imagens_geradas' in st.session_state and st.session_state['imagens_geradas']:
    if st.sidebar.button("Limpar Prévias e Recomeçar", use_container_width=True):
        st.session_state['imagens_geradas'] = None
        st.rerun()

    st.markdown("---")
    imagens_para_pdf = st.session_state['imagens_geradas']
    pdf_bytes = io.BytesIO()
    imagens_para_pdf[0].save(pdf_bytes, format="PDF", save_all=True, append_images=imagens_para_pdf[1:])
    pdf_bytes.seek(0)
    
    st.download_button("⬇️ Baixar PDF com Todas as Comandas", data=pdf_bytes, file_name=f"comandas.pdf", mime="application/pdf", use_container_width=True)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("comandas.pdf", pdf_bytes.getvalue())
    zip_buffer.seek(0)
    st.download_button(label="⬇️ Baixar PDF Compactado (.zip)", data=zip_buffer, file_name=f"comandas.zip", mime="application/zip", use_container_width=True)
    
    st.markdown("---")
    for i, img in enumerate(imagens_para_pdf):
        st.image(img, caption=f"Prévia da Comanda Nº {st.session_state.get('inicio', 1) + i}", width=600)

elif imagem_base_up:
    imagem_base_up.seek(0)
    st.image(imagem_base_up, caption="O seu template. Preencha os dados para continuar.", width=600)
else:
    st.info("A pré-visualização das suas comandas aparecerá aqui.")

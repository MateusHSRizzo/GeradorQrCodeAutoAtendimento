"""
core.py — Lógica central do Gerador de Comandas
Sem dependências do Streamlit — reutilizável por app.py e api.py
"""

import base64
import csv
import hashlib
import io
import json
import os
import re
import smtplib
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import lru_cache
from typing import Callable, Optional

import qrcode
from barcode import Code39
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont

# ── Dependências opcionais ──────────────────────────────────────
try:
    from pyzbar.pyzbar import decode as _pyzbar_decode
    PYZBAR_DISPONIVEL = True
except (ImportError, Exception):
    PYZBAR_DISPONIVEL = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Constantes ──────────────────────────────────────────────────
ARQUIVO_PERFIS   = "profiles.json"
ARQUIVO_AUDITORIA = "audit_log.csv"

TAMANHOS_PAGINA: dict[str, tuple[int, int]] = {
    "A4 — 150 DPI":   (1240, 1754),
    "A4 — 300 DPI":   (2480, 3508),
    "A5 — 150 DPI":   (874,  1240),
    "A5 — 300 DPI":   (1748, 2480),
    "Carta — 150 DPI":(1275, 1650),
}

ANCORAS_WATERMARK = [
    "top-left", "top-center", "top-right",
    "middle-left", "center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
]


# ═══════════════════════════════════════════════════════════════
# 1. VALIDAÇÃO DE DOCUMENTOS
# ═══════════════════════════════════════════════════════════════

def validar_documento(documento: str, tipo: str) -> tuple[bool, str]:
    numeros = re.sub(r"\D", "", documento)
    if tipo == "CPF":
        ok = len(numeros) == 11
        return ok, "" if ok else f"CPF deve ter 11 dígitos (tem {len(numeros)})."
    if tipo == "CNPJ":
        ok = len(numeros) == 14
        return ok, "" if ok else f"CNPJ deve ter 14 dígitos (tem {len(numeros)})."
    return False, "Tipo de documento desconhecido."


def aplicar_mascara_qrcode(documento: str, tipo: str) -> str:
    """Formata CPF/CNPJ e adiciona ':' — lógica preservada integralmente."""
    numeros = re.sub(r"\D", "", documento)
    if tipo == "CPF" and numeros:
        numeros = numeros[:11]
        mascara = (
            f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:11]}"
            if len(numeros) == 11 else numeros
        )
    elif tipo == "CNPJ" and numeros:
        numeros = numeros[:14]
        mascara = (
            f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/{numeros[8:12]}-{numeros[12:14]}"
            if len(numeros) == 14 else numeros
        )
    else:
        mascara = numeros
    return mascara + ":"


# ═══════════════════════════════════════════════════════════════
# 2. GERAÇÃO DE QR CODE  ← lógica de URL preservada
# ═══════════════════════════════════════════════════════════════

@lru_cache(maxsize=2048)
def _gerar_qrcode_bytes(
    numero: int,
    dado_base: str,
    tamanho: int,
    rotacao: int,
    fill_color: str,
    back_color: str,
) -> bytes:
    """Gera QR Code e retorna bytes PNG. Cacheado via lru_cache."""
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
    img_qr = qr.make_image(
        fill_color=fill_color,
        back_color=back_color,
    ).convert("RGBA")
    img_qr = img_qr.resize((tamanho, tamanho), Image.Resampling.NEAREST)
    if rotacao:
        img_qr = img_qr.rotate(rotacao, expand=True)

    buf = io.BytesIO()
    img_qr.save(buf, format="PNG")
    return buf.getvalue()


def gerar_qrcode_imagem(
    numero: int,
    dado_base: str,
    tamanho: int,
    rotacao: int,
    fill_color: str = "#000000",
    back_color: str = "#FFFFFF",
) -> Image.Image:
    return Image.open(io.BytesIO(
        _gerar_qrcode_bytes(numero, dado_base, tamanho, rotacao, fill_color, back_color)
    ))


def gerar_url_qrcode(numero: int, dado_base: str) -> str:
    """Retorna a URL completa que será codificada no QR."""
    texto_original = f"{dado_base}{numero}"
    b64 = base64.b64encode(texto_original.encode()).decode()
    return f"https://pediucomeu.com.br/autoatendimento/{b64}"


# ═══════════════════════════════════════════════════════════════
# 3. GERAÇÃO DE CÓDIGO DE BARRAS
# ═══════════════════════════════════════════════════════════════

def gerar_code39(
    numero: int,
    prefixo: str,
    largura: int,
    altura: int,
    corte_vertical: int,
    rotacao: int,
    corte_esq: int,
    corte_dir: int,
) -> Image.Image:
    codigo = f"{prefixo}{str(numero).zfill(4)}"
    writer = ImageWriter()
    writer.set_options({
        "module_width": 0.7,
        "module_height": altura / 10,
        "quiet_zone": 2.0,
        "font_size": 0,
        "text_distance": 0,
        "write_text": False,
    })
    barcode_obj = Code39(codigo, writer=writer, add_checksum=False)
    out = io.BytesIO()
    barcode_obj.write(out)
    out.seek(0)
    img = Image.open(out)

    lw, lh = img.size
    cut_h = int(lh * (1 - corte_vertical / 100))
    esq_px = int(lw * corte_esq / 100)
    dir_px = int(lw * (1 - corte_dir / 100))
    img = img.crop((esq_px, 0, dir_px, cut_h))
    img = img.resize((largura, altura), Image.Resampling.NEAREST)
    if rotacao:
        img = img.rotate(rotacao, expand=True)
    return img


# ═══════════════════════════════════════════════════════════════
# 4. UTILITÁRIOS DE FONTE E TEXTO
# ═══════════════════════════════════════════════════════════════

def carregar_fontes_disponiveis(pasta: str = "fonts") -> dict[str, str]:
    fontes: dict[str, str] = {}
    if not os.path.isdir(pasta):
        return fontes
    for nome_f in sorted(os.listdir(pasta)):
        if nome_f.lower().endswith(".ttf"):
            caminho = os.path.join(pasta, nome_f)
            try:
                font = ImageFont.truetype(caminho, 10)
                nome_real = " ".join(font.getname())
                fontes[nome_real] = caminho
            except Exception:
                fontes[os.path.splitext(nome_f)[0]] = caminho
    return fontes


def carregar_fonte(
    caminho: str, tamanho: int
) -> Optional[ImageFont.FreeTypeFont]:
    try:
        return ImageFont.truetype(caminho, tamanho)
    except Exception:
        return None


def _colar_texto(
    draw: ImageDraw.ImageDraw,
    img_final: Image.Image,
    texto: str,
    fonte: ImageFont.FreeTypeFont,
    x: int, y: int,
    cor: str,
    rotacao: int,
) -> None:
    bbox = draw.textbbox((0, 0), texto, font=fonte)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if rotacao == 0:
        draw.text((x - w // 2, y - h // 2), texto, font=fonte, fill=cor)
    else:
        tmp = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(tmp)
        d.text((-bbox[0], -bbox[1]), texto, font=fonte, fill=cor)
        tmp = tmp.rotate(rotacao, expand=True, fillcolor=(0, 0, 0, 0))
        rw, rh = tmp.size
        img_final.paste(tmp, (x - rw // 2, y - rh // 2), tmp)


# ═══════════════════════════════════════════════════════════════
# 5. COMPOSIÇÃO DAS IMAGENS FINAIS
# ═══════════════════════════════════════════════════════════════

def _aplicar_watermark_interno(
    img: Image.Image,
    wm_config: dict,
) -> Image.Image:
    logo: Optional[Image.Image] = wm_config.get("logo")
    if logo is None:
        return img
    posicao  = wm_config.get("posicao", "bottom-right")
    escala   = wm_config.get("escala", 15)
    opacidade = wm_config.get("opacidade", 70)

    img = img.convert("RGBA")
    logo = logo.convert("RGBA")

    max_dim = min(img.width, img.height)
    target  = int(max_dim * escala / 100)
    ratio   = target / max(logo.width, logo.height)
    nw, nh  = int(logo.width * ratio), int(logo.height * ratio)
    logo_r  = logo.resize((nw, nh), Image.Resampling.LANCZOS)

    r, g, b, a = logo_r.split()
    a = a.point(lambda p: int(p * opacidade / 100))
    logo_r.putalpha(a)

    m = 20
    ancoras = {
        "top-left":      (m, m),
        "top-center":    ((img.width - nw) // 2, m),
        "top-right":     (img.width - nw - m, m),
        "middle-left":   (m, (img.height - nh) // 2),
        "center":        ((img.width - nw) // 2, (img.height - nh) // 2),
        "middle-right":  (img.width - nw - m, (img.height - nh) // 2),
        "bottom-left":   (m, img.height - nh - m),
        "bottom-center": ((img.width - nw) // 2, img.height - nh - m),
        "bottom-right":  (img.width - nw - m, img.height - nh - m),
    }
    pos = ancoras.get(posicao, ancoras["bottom-right"])
    img.paste(logo_r, pos, logo_r)
    return img.convert("RGB")


def gerar_imagem_qrcode(
    background: Image.Image,
    numero: int,
    dado_base: str,
    config: dict,
    watermark_config: Optional[dict] = None,
) -> Optional[Image.Image]:
    imagem = background.copy().convert("RGBA")
    draw   = ImageDraw.Draw(imagem)

    img_qr = gerar_qrcode_imagem(
        numero, dado_base,
        config["tamanho_qr"], config["rotacao_qr"],
        config.get("fill_color", "#000000"),
        config.get("back_color", "#FFFFFF"),
    )
    qw, qh = img_qr.size
    imagem.paste(img_qr, (config["qr_x"] - qw // 2, config["qr_y"] - qh // 2), img_qr)

    fonte = carregar_fonte(config["caminho_fonte"], config["tamanho_texto"])
    if fonte is None:
        return None
    _colar_texto(draw, imagem, str(numero), fonte,
                 config["texto_x"], config["texto_y"],
                 config["cor_texto"], config["rotacao_texto"])

    resultado = imagem.convert("RGB")
    if watermark_config:
        resultado = _aplicar_watermark_interno(resultado, watermark_config)
    return resultado


def gerar_imagem_barcode(
    background: Image.Image,
    numero: int,
    config: dict,
    watermark_config: Optional[dict] = None,
) -> Optional[Image.Image]:
    imagem = background.copy().convert("RGBA")
    draw   = ImageDraw.Draw(imagem)

    bar = gerar_code39(
        numero, config["prefixo"],
        config["largura"], config["altura"],
        config["corte_vertical"], config["rotacao_barra"],
        config["corte_esq"], config["corte_dir"],
    ).convert("RGBA")
    bw, bh = bar.size
    imagem.paste(bar, (config["bar_x"] - bw // 2, config["bar_y"] - bh // 2), bar)

    fonte = carregar_fonte(config["caminho_fonte"], config["tamanho_texto"])
    if fonte is None:
        return None
    _colar_texto(draw, imagem, str(numero).zfill(4), fonte,
                 config["texto_x"], config["texto_y"],
                 config["cor_texto"], config["rotacao_texto"])

    resultado = imagem.convert("RGB")
    if watermark_config:
        resultado = _aplicar_watermark_interno(resultado, watermark_config)
    return resultado


# ═══════════════════════════════════════════════════════════════
# 6. GERAÇÃO EM LOTE (paralela)
# ═══════════════════════════════════════════════════════════════

def gerar_lista_imagens(
    modo: str,
    background: Image.Image,
    inicio: int,
    fim: int,
    dado_base: str,
    config: dict,
    watermark_config: Optional[dict] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> tuple[list[Image.Image], list[int]]:
    total = fim - inicio + 1
    resultados: dict[int, Optional[Image.Image]] = {}

    def gerar_uma(n: int) -> tuple[int, Optional[Image.Image]]:
        if modo == "QR Code":
            return n, gerar_imagem_qrcode(background, n, dado_base, config, watermark_config)
        return n, gerar_imagem_barcode(background, n, config, watermark_config)

    with ThreadPoolExecutor(max_workers=min(8, total)) as ex:
        futures = {ex.submit(gerar_uma, n): n for n in range(inicio, fim + 1)}
        done = 0
        for fut in as_completed(futures):
            n, img = fut.result()
            resultados[n] = img
            done += 1
            if progress_cb:
                progress_cb(done, total)

    imagens, falhas = [], []
    for n in range(inicio, fim + 1):
        img = resultados.get(n)
        if img is not None:
            imagens.append(img)
        else:
            falhas.append(n)
    return imagens, falhas


# ═══════════════════════════════════════════════════════════════
# 7. GRADE DE IMPRESSÃO (múltiplas comandas por página)
# ═══════════════════════════════════════════════════════════════

def gerar_grade_pagina(
    imagens: list[Image.Image],
    cols: int,
    rows: int,
    page_w: int,
    page_h: int,
    margem: int = 40,
    gap: int = 10,
) -> list[Image.Image]:
    if not imagens:
        return []
    cell_w = (page_w - 2 * margem - max(cols - 1, 0) * gap) // cols
    cell_h = (page_h - 2 * margem - max(rows - 1, 0) * gap) // rows
    por_pagina = cols * rows
    paginas = []

    for i in range(0, len(imagens), por_pagina):
        pagina = Image.new("RGB", (page_w, page_h), "white")
        lote   = imagens[i:i + por_pagina]
        for j, img in enumerate(lote):
            col = j % cols
            row = j // cols
            sc  = min(cell_w / img.width, cell_h / img.height)
            nw, nh = int(img.width * sc), int(img.height * sc)
            img_s = img.resize((nw, nh), Image.Resampling.LANCZOS)
            x = margem + col * (cell_w + gap) + (cell_w - nw) // 2
            y = margem + row * (cell_h + gap) + (cell_h - nh) // 2
            pagina.paste(img_s, (x, y))
        paginas.append(pagina)
    return paginas


# ═══════════════════════════════════════════════════════════════
# 8. EXPORTAÇÃO
# ═══════════════════════════════════════════════════════════════

def exportar_pdf(imagens: list[Image.Image], dpi: int = 150) -> bytes:
    buf = io.BytesIO()
    imagens[0].save(
        buf, format="PDF", save_all=True,
        append_images=imagens[1:], resolution=dpi,
    )
    buf.seek(0)
    return buf.getvalue()


def exportar_zip_pngs(imagens: list[Image.Image], inicio: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, img in enumerate(imagens, start=inicio):
            pb = io.BytesIO()
            img.save(pb, format="PNG")
            zf.writestr(f"comanda_{str(idx).zfill(4)}.png", pb.getvalue())
    buf.seek(0)
    return buf.getvalue()


def calcular_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════
# 9. VALIDAÇÃO DE QR GERADO (pyzbar)
# ═══════════════════════════════════════════════════════════════

def validar_qrs_em_lote(
    numeros: list[int],
    dado_base: str,
    fill_color: str = "#000000",
    back_color: str = "#FFFFFF",
) -> list[dict]:
    """
    Valida uma lista de números gerando e decodificando cada QR.
    Retorna lista de {'numero', 'url_esperada', 'url_lida', 'ok'}.
    """
    resultados = []
    for numero in numeros:
        url_esperada = gerar_url_qrcode(numero, dado_base)
        if not PYZBAR_DISPONIVEL:
            resultados.append({
                "numero": numero,
                "url_esperada": url_esperada,
                "url_lida": "—",
                "ok": None,  # indeterminado
            })
            continue

        qr_bytes = _gerar_qrcode_bytes(
            numero, dado_base, 300, 0, fill_color, back_color
        )
        img = Image.open(io.BytesIO(qr_bytes))
        decoded = _pyzbar_decode(img)
        if decoded:
            url_lida = decoded[0].data.decode()
            ok = url_lida == url_esperada
        else:
            url_lida = "❌ não decodificado"
            ok = False

        resultados.append({
            "numero": numero,
            "url_esperada": url_esperada,
            "url_lida": url_lida,
            "ok": ok,
        })
    return resultados


# ═══════════════════════════════════════════════════════════════
# 10. CONTRASTE E SIMULAÇÃO DE IMPRESSÃO
# ═══════════════════════════════════════════════════════════════

def _luminancia_relativa(hex_cor: str) -> float:
    hex_cor = hex_cor.lstrip("#")
    r, g, b = [int(hex_cor[i:i+2], 16) / 255 for i in (0, 2, 4)]

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def calcular_contraste_wcag(cor1: str, cor2: str) -> float:
    """Razão de contraste WCAG entre duas cores hex."""
    l1 = _luminancia_relativa(cor1)
    l2 = _luminancia_relativa(cor2)
    lh, ld = max(l1, l2), min(l1, l2)
    return (lh + 0.05) / (ld + 0.05)


def simular_escala_cinza(img: Image.Image) -> Image.Image:
    return img.convert("L").convert("RGB")


def calcular_contraste_michelson(img: Image.Image) -> float:
    """Contraste Michelson (0–1) de uma imagem (útil para verificar legibilidade)."""
    gray = list(img.convert("L").getdata())
    lmax, lmin = max(gray), min(gray)
    if lmax + lmin == 0:
        return 0.0
    return (lmax - lmin) / (lmax + lmin)


# ═══════════════════════════════════════════════════════════════
# 11. IMPORTAÇÃO VIA CSV
# ═══════════════════════════════════════════════════════════════

def processar_csv(
    csv_bytes: bytes,
    background: Image.Image,
    config: dict,
    dado_base_padrao: str,
    watermark_config: Optional[dict] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> tuple[list[Image.Image], list[str], list[dict]]:
    """
    CSV esperado: colunas 'numero' (obrigatória), 'documento' (opcional), 'nome' (opcional).
    Retorna (imagens, erros, metadados_por_linha).
    """
    try:
        texto = csv_bytes.decode("utf-8-sig", errors="replace")
        reader = list(csv.DictReader(io.StringIO(texto)))
    except Exception as e:
        return [], [f"Erro ao ler CSV: {e}"], []

    if not reader:
        return [], ["CSV vazio ou sem cabeçalho."], []

    if "numero" not in reader[0]:
        colunas = list(reader[0].keys())
        return [], [f"Coluna 'numero' não encontrada. Colunas detectadas: {colunas}"], []

    imagens, erros, metadados = [], [], []
    total = len(reader)

    for i, linha in enumerate(reader):
        try:
            numero = int(str(linha["numero"]).strip())
        except (ValueError, KeyError):
            erros.append(f"Linha {i+2}: número inválido → '{linha.get('numero', '')}'")
            continue

        doc_linha = str(linha.get("documento", "")).strip()
        if doc_linha:
            nums = re.sub(r"\D", "", doc_linha)
            tipo_linha = "CNPJ" if len(nums) == 14 else "CPF"
            dado_base_linha = aplicar_mascara_qrcode(doc_linha, tipo_linha)
        else:
            dado_base_linha = dado_base_padrao

        img = gerar_imagem_qrcode(
            background, numero, dado_base_linha, config, watermark_config
        )
        if img:
            imagens.append(img)
            metadados.append({
                "numero": numero,
                "documento": doc_linha or "—",
                "nome": str(linha.get("nome", "")).strip() or "—",
            })
        else:
            erros.append(f"Linha {i+2}: falha ao gerar comanda {numero}")

        if progress_cb:
            progress_cb(i + 1, total)

    return imagens, erros, metadados


# ═══════════════════════════════════════════════════════════════
# 12. ENVIO POR E-MAIL
# ═══════════════════════════════════════════════════════════════

def enviar_email(
    destinatario: str,
    pdf_bytes: bytes,
    nome_arquivo: str = "comandas.pdf",
    assunto: str = "Comandas Geradas",
    corpo: str = "Segue em anexo o PDF com as comandas geradas.",
) -> tuple[bool, str]:
    host     = os.environ.get("EMAIL_HOST", "")
    port     = int(os.environ.get("EMAIL_PORT", "587"))
    user     = os.environ.get("EMAIL_USER", "")
    password = os.environ.get("EMAIL_PASS", "")

    if not all([host, user, password]):
        return False, (
            "Credenciais SMTP não configuradas. "
            "Crie um arquivo .env com EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASS."
        )

    msg = MIMEMultipart()
    msg["From"], msg["To"], msg["Subject"] = user, destinatario, assunto
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    part = MIMEBase("application", "pdf")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{nome_arquivo}"')
    msg.attach(part)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port) as srv:
                srv.login(user, password)
                srv.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as srv:
                srv.ehlo()
                srv.starttls()
                srv.login(user, password)
                srv.send_message(msg)
        return True, f"E-mail enviado com sucesso para {destinatario}"
    except Exception as e:
        return False, f"Erro ao enviar: {e}"


# ═══════════════════════════════════════════════════════════════
# 13. PERFIS DE CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════

def carregar_perfis() -> dict:
    if not os.path.isfile(ARQUIVO_PERFIS):
        return {}
    try:
        with open(ARQUIVO_PERFIS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def salvar_perfil(nome: str, config: dict) -> None:
    perfis = carregar_perfis()
    perfis[nome] = {
        "config": config,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(ARQUIVO_PERFIS, "w", encoding="utf-8") as f:
        json.dump(perfis, f, ensure_ascii=False, indent=2)


def deletar_perfil(nome: str) -> None:
    perfis = carregar_perfis()
    perfis.pop(nome, None)
    with open(ARQUIVO_PERFIS, "w", encoding="utf-8") as f:
        json.dump(perfis, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# 14. AUDITORIA
# ═══════════════════════════════════════════════════════════════

def registrar_auditoria(
    modo: str,
    documento: str,
    inicio: int,
    fim: int,
    total: int,
    dpi: int,
    pdf_hash: str,
    tamanho_kb: float,
) -> None:
    existe = os.path.isfile(ARQUIVO_AUDITORIA)
    with open(ARQUIVO_AUDITORIA, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not existe:
            w.writerow([
                "timestamp", "modo", "documento", "inicio", "fim",
                "total", "dpi", "sha256_16", "tamanho_kb",
            ])
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            modo, documento, inicio, fim, total, dpi,
            pdf_hash, f"{tamanho_kb:.1f}",
        ])


def ler_auditoria() -> list[dict]:
    if not os.path.isfile(ARQUIVO_AUDITORIA):
        return []
    try:
        with open(ARQUIVO_AUDITORIA, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
# 15. RÉGUAS E GUIAS (utilitário de preview)
# ═══════════════════════════════════════════════════════════════

def draw_rulers_and_guides(
    image: Image.Image,
    guides: dict,
    ruler_size: int = 30,
) -> Image.Image:
    ow, oh = image.size
    canvas = Image.new("RGB", (ow + ruler_size, oh + ruler_size), "#f0f2f6")
    canvas.paste(image, (ruler_size, ruler_size))
    draw = ImageDraw.Draw(canvas)

    ruler_font = ImageFont.load_default()
    for candidato in ["DejaVuSans.ttf", "LiberationSans-Regular.ttf",
                       "arial.ttf", "Arial.ttf"]:
        try:
            ruler_font = ImageFont.truetype(candidato, 10)
            break
        except IOError:
            continue

    for x in range(0, ow, 10):
        px = x + ruler_size
        if x % 100 == 0:
            draw.line([(px, 0), (px, ruler_size)], fill="black", width=1)
            txt = str(x)
            bb = draw.textbbox((0, 0), txt, font=ruler_font)
            draw.text((px - (bb[2]-bb[0])//2, 5), txt, fill="black", font=ruler_font)
        elif x % 50 == 0:
            draw.line([(px, ruler_size//2), (px, ruler_size)], fill="gray", width=1)
        else:
            draw.line([(px, ruler_size*3//4), (px, ruler_size)], fill="lightgray", width=1)

    for y in range(0, oh, 10):
        py = y + ruler_size
        if y % 100 == 0:
            draw.line([(0, py), (ruler_size, py)], fill="black", width=1)
            txt = str(y)
            bb = draw.textbbox((0, 0), txt, font=ruler_font)
            draw.text((5, py - (bb[3]-bb[1])//2), txt, fill="black", font=ruler_font)
        elif y % 50 == 0:
            draw.line([(ruler_size//2, py), (ruler_size, py)], fill="gray", width=1)
        else:
            draw.line([(ruler_size*3//4, py), (ruler_size, py)], fill="lightgray", width=1)

    nw, nh = canvas.size
    for _name, pos in guides.items():
        color = pos["color"]
        if "x" in pos:
            gx = pos["x"] + ruler_size
            draw.line([(gx, 0), (gx, nh)], fill=color, width=1)
        if "y" in pos:
            gy = pos["y"] + ruler_size
            draw.line([(0, gy), (nw, gy)], fill=color, width=1)

    return canvas


# ═══════════════════════════════════════════════════════════════
# 16. NUMERAÇÃO NÃO-SEQUENCIAL
# ═══════════════════════════════════════════════════════════════

def parsear_lista_numeros(expr: str) -> tuple[list[int], str]:
    """
    Converte expressão como '1,3,5,10-20,50' em lista ordenada de inteiros.
    Retorna (lista, mensagem_de_erro).
    """
    numeros: set[int] = set()
    expr = expr.strip()
    if not expr:
        return [], "Expressão vazia."
    for parte in expr.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "-" in parte:
            segmentos = parte.split("-")
            if len(segmentos) == 2:
                try:
                    a, b = int(segmentos[0]), int(segmentos[1])
                    if b < a:
                        return [], f"Intervalo inválido: {parte}"
                    if b - a > 10_000:
                        return [], f"Intervalo muito grande (máx 10 000): {parte}"
                    numeros.update(range(a, b + 1))
                except ValueError:
                    return [], f"Valor inválido: '{parte}'"
            else:
                return [], f"Intervalo malformado: '{parte}'"
        else:
            try:
                numeros.add(int(parte))
            except ValueError:
                return [], f"Número inválido: '{parte}'"
    return sorted(numeros), ""


# ═══════════════════════════════════════════════════════════════
# 17. QR CODE COM LOGO EMBUTIDO
# ═══════════════════════════════════════════════════════════════

@lru_cache(maxsize=512)
def _gerar_qrcode_bytes_alto(
    numero: int, dado_base: str, tamanho: int,
    rotacao: int, fill_color: str, back_color: str,
) -> bytes:
    """QR Code com correção de erro nível H (necessário para logo embutido)."""
    texto = f"{dado_base}{numero}"
    b64   = base64.b64encode(texto.encode()).decode()
    url   = f"https://pediucomeu.com.br/autoatendimento/{b64}"

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10, border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color=back_color).convert("RGBA")
    img = img.resize((tamanho, tamanho), Image.Resampling.NEAREST)
    if rotacao:
        img = img.rotate(rotacao, expand=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def gerar_qrcode_com_logo(
    numero: int,
    dado_base: str,
    tamanho: int,
    fill_color: str = "#000000",
    back_color: str = "#FFFFFF",
    logo: Optional[Image.Image] = None,
    logo_pct: int = 25,
    rotacao: int = 0,
) -> Image.Image:
    qr_bytes = _gerar_qrcode_bytes_alto(
        numero, dado_base, tamanho, 0, fill_color, back_color
    )
    img_qr = Image.open(io.BytesIO(qr_bytes)).convert("RGBA")

    if logo is not None:
        max_dim = int(tamanho * logo_pct / 100)
        logo_r  = logo.convert("RGBA")
        ratio   = max_dim / max(logo_r.width, logo_r.height)
        lw, lh  = int(logo_r.width * ratio), int(logo_r.height * ratio)
        logo_r  = logo_r.resize((lw, lh), Image.Resampling.LANCZOS)

        # Fundo branco atrás do logo
        fundo = Image.new("RGBA", (lw + 8, lh + 8), back_color)
        fundo.paste(logo_r, (4, 4), logo_r)
        px = (tamanho - fundo.width)  // 2
        py = (tamanho - fundo.height) // 2
        img_qr.paste(fundo, (px, py), fundo)

    if rotacao:
        img_qr = img_qr.rotate(rotacao, expand=True)
    return img_qr


def gerar_imagem_qrcode_com_logo(
    background: Image.Image,
    numero: int,
    dado_base: str,
    config: dict,
    logo_config: Optional[dict] = None,
    watermark_config: Optional[dict] = None,
) -> Optional[Image.Image]:
    imagem = background.copy().convert("RGBA")
    draw   = ImageDraw.Draw(imagem)

    logo = logo_config.get("logo") if logo_config else None
    logo_pct = logo_config.get("pct", 25) if logo_config else 25

    img_qr = gerar_qrcode_com_logo(
        numero, dado_base,
        config["tamanho_qr"],
        config.get("fill_color", "#000000"),
        config.get("back_color", "#FFFFFF"),
        logo, logo_pct,
        config.get("rotacao_qr", 0),
    )
    qw, qh = img_qr.size
    imagem.paste(img_qr, (config["qr_x"] - qw // 2, config["qr_y"] - qh // 2), img_qr)

    fonte = carregar_fonte(config["caminho_fonte"], config["tamanho_texto"])
    if fonte is None:
        return None
    _colar_texto(draw, imagem, str(numero), fonte,
                 config["texto_x"], config["texto_y"],
                 config["cor_texto"], config.get("rotacao_texto", 0))

    # Campos variáveis extras
    for campo in config.get("campos_extras", []):
        fonte_c = carregar_fonte(campo.get("caminho_fonte", config["caminho_fonte"]),
                                  campo.get("tamanho", 60))
        if fonte_c:
            texto_c = campo["texto"].replace("{numero}", str(numero))
            _colar_texto(draw, imagem, texto_c, fonte_c,
                         campo["x"], campo["y"],
                         campo.get("cor", "#000000"), campo.get("rotacao", 0))

    resultado = imagem.convert("RGB")
    if watermark_config:
        resultado = _aplicar_watermark_interno(resultado, watermark_config)
    return resultado


# ═══════════════════════════════════════════════════════════════
# 18. SÉRIE, PREFIXO E SUFIXO
# ═══════════════════════════════════════════════════════════════

def formatar_numero_serie(
    numero: int,
    prefixo: str = "",
    sufixo: str = "",
    padding: int = 4,
) -> str:
    num_str = str(numero).zfill(padding) if padding > 0 else str(numero)
    return f"{prefixo}{num_str}{sufixo}"


# ═══════════════════════════════════════════════════════════════
# 19. QR TOKEN ÚNICO POR COMANDA
# ═══════════════════════════════════════════════════════════════

import uuid as _uuid

def gerar_url_com_token(numero: int, dado_base: str) -> tuple[str, str]:
    """
    Gera URL com token UUID único.
    Retorna (url, token). Requer mudança server-side para validar o token.
    """
    token = _uuid.uuid4().hex[:10]
    texto = f"{dado_base}{numero}"
    b64   = base64.b64encode(texto.encode()).decode()
    url   = f"https://pediucomeu.com.br/autoatendimento/{b64}?t={token}"
    return url, token


def salvar_tokens(tokens_map: dict[int, str], nome_arquivo: str) -> None:
    """Salva mapa {numero: token} em JSON para rastreabilidade."""
    with open(nome_arquivo, "w", encoding="utf-8") as f:
        json.dump({"tokens": tokens_map,
                   "gerado_em": datetime.now().isoformat()}, f, indent=2)


def gerar_qrcode_token(
    numero: int,
    dado_base: str,
    tamanho: int,
    fill_color: str = "#000000",
    back_color: str = "#FFFFFF",
    rotacao: int = 0,
) -> tuple[Image.Image, str]:
    """Gera QR com token único. Retorna (imagem_qr, token)."""
    token = _uuid.uuid4().hex[:10]
    texto = f"{dado_base}{numero}"
    b64   = base64.b64encode(texto.encode()).decode()
    url   = f"https://pediucomeu.com.br/autoatendimento/{b64}?t={token}"

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10, border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color=back_color).convert("RGBA")
    img = img.resize((tamanho, tamanho), Image.Resampling.NEAREST)
    if rotacao:
        img = img.rotate(rotacao, expand=True)
    return img, token


# ═══════════════════════════════════════════════════════════════
# 20. MARCAS DE CORTE / SANGRIA (BLEED)
# ═══════════════════════════════════════════════════════════════

def adicionar_marcas_corte(
    img: Image.Image,
    bleed_px: int = 30,
    mark_len: int = 15,
    mark_color: str = "#000000",
) -> Image.Image:
    """
    Adiciona área de sangria e marcas de corte profissionais.
    bleed_px: pixels de sangria em cada lado.
    """
    ow, oh = img.size
    nw, nh = ow + bleed_px * 2, oh + bleed_px * 2
    canvas = Image.new("RGB", (nw, nh), "white")
    canvas.paste(img, (bleed_px, bleed_px))
    draw = ImageDraw.Draw(canvas)

    offset = 3  # gap entre borda da imagem e a marca
    ml = mark_len

    corners = [
        (bleed_px, bleed_px),          # top-left
        (bleed_px + ow, bleed_px),     # top-right
        (bleed_px, bleed_px + oh),     # bottom-left
        (bleed_px + ow, bleed_px + oh) # bottom-right
    ]
    for cx, cy in corners:
        # horizontal mark
        dir_x = -1 if cx > nw // 2 else 1
        draw.line([(cx + dir_x * offset, cy),
                   (cx + dir_x * (offset + ml), cy)],
                  fill=mark_color, width=1)
        # vertical mark
        dir_y = -1 if cy > nh // 2 else 1
        draw.line([(cx, cy + dir_y * offset),
                   (cx, cy + dir_y * (offset + ml))],
                  fill=mark_color, width=1)

    # Linha tracejada de corte
    dash = 5
    for x in range(0, nw, dash * 2):
        if x + dash < nw:
            draw.line([(x, bleed_px), (x + dash, bleed_px)],
                      fill="#aaaaaa", width=1)
            draw.line([(x, bleed_px + oh), (x + dash, bleed_px + oh)],
                      fill="#aaaaaa", width=1)
    for y in range(0, nh, dash * 2):
        if y + dash < nh:
            draw.line([(bleed_px, y), (bleed_px, y + dash)],
                      fill="#aaaaaa", width=1)
            draw.line([(bleed_px + ow, y), (bleed_px + ow, y + dash)],
                      fill="#aaaaaa", width=1)
    return canvas


# ═══════════════════════════════════════════════════════════════
# 21. FOLHA DE CALIBRAÇÃO DE IMPRESSORA
# ═══════════════════════════════════════════════════════════════

def gerar_folha_calibracao(
    dado_base: str,
    config: dict,
    numero_exemplo: int = 1,
    tamanhos_pct: list[int] = None,
) -> Image.Image:
    """
    Gera uma folha A4 com QRs em múltiplos tamanhos e régua de calibração.
    """
    if tamanhos_pct is None:
        tamanhos_pct = [50, 75, 100, 125, 150]

    page_w, page_h = 1240, 1754  # A4 a 150 DPI
    page = Image.new("RGB", (page_w, page_h), "white")
    draw = ImageDraw.Draw(page)

    ruler_font = ImageFont.load_default()
    for candidato in ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf"]:
        try:
            ruler_font = ImageFont.truetype(candidato, 18)
            break
        except IOError:
            continue

    tamanho_base = config.get("tamanho_qr", 300)
    cell_w = page_w // len(tamanhos_pct)
    y_start = 80

    draw.text((20, 20), "FOLHA DE CALIBRAÇÃO — Gerador de Comandas",
              fill="#333333", font=ruler_font)
    draw.text((20, 45), f"Imprima e verifique qual tamanho lê corretamente com seu scanner.",
              fill="#666666", font=ruler_font)

    for i, pct in enumerate(tamanhos_pct):
        tamanho = int(tamanho_base * pct / 100)
        tamanho = max(50, tamanho)
        img_qr = gerar_qrcode_imagem(
            numero_exemplo, dado_base, tamanho, 0,
            config.get("fill_color", "#000000"),
            config.get("back_color", "#FFFFFF"),
        )
        cx = i * cell_w + (cell_w - tamanho) // 2
        page.paste(img_qr.convert("RGB"), (cx, y_start))
        label = f"{pct}% ({tamanho}px)"
        bb = draw.textbbox((0, 0), label, font=ruler_font)
        lw = bb[2] - bb[0]
        draw.text((i * cell_w + (cell_w - lw) // 2, y_start + tamanho + 6),
                  label, fill="#333333", font=ruler_font)

    # Régua horizontal de 15cm
    ruler_y = y_start + int(tamanho_base * 1.5) + 60
    px_per_mm = 150 / 25.4  # 150 DPI → pixels por mm
    for mm in range(0, 151):
        x = int(20 + mm * px_per_mm)
        if x >= page_w - 20:
            break
        h = 20 if mm % 10 == 0 else (12 if mm % 5 == 0 else 7)
        draw.line([(x, ruler_y), (x, ruler_y + h)], fill="#333333", width=1)
        if mm % 10 == 0:
            txt = f"{mm}mm"
            draw.text((x + 2, ruler_y + 22), txt, fill="#333333", font=ruler_font)
    draw.line([(20, ruler_y), (int(20 + 150 * px_per_mm), ruler_y)],
              fill="#333333", width=2)
    draw.text((20, ruler_y - 25), "Régua de calibração (150mm):",
              fill="#555555", font=ruler_font)

    return page


# ═══════════════════════════════════════════════════════════════
# 22. ETIQUETAS AVERY
# ═══════════════════════════════════════════════════════════════

# Medidas a 150 DPI. Todos os valores em pixels.
# Fonte: dimensões oficiais Avery convertidas de polegadas × 150.
TEMPLATES_AVERY: dict[str, dict] = {
    "Avery 5160 — 3×10 (2,625\"×1\")": {
        "cols": 3, "rows": 10,
        "page_w": 1275, "page_h": 1650,
        "cell_w": 394, "cell_h": 150,
        "margin_left": 46, "margin_top": 75,
        "gap_h": 0, "gap_v": 0,
    },
    "Avery 5163 — 2×5 (4\"×2\")": {
        "cols": 2, "rows": 5,
        "page_w": 1275, "page_h": 1650,
        "cell_w": 600, "cell_h": 300,
        "margin_left": 38, "margin_top": 75,
        "gap_h": 0, "gap_v": 0,
    },
    "Avery 5167 — 4×20 (1,75\"×0,5\")": {
        "cols": 4, "rows": 20,
        "page_w": 1275, "page_h": 1650,
        "cell_w": 263, "cell_h": 75,
        "margin_left": 75, "margin_top": 75,
        "gap_h": 0, "gap_v": 0,
    },
    "Avery L7160 — 3×7 (63,5mm×38,1mm) A4": {
        "cols": 3, "rows": 7,
        "page_w": 1240, "page_h": 1754,
        "cell_w": 374, "cell_h": 224,
        "margin_left": 47, "margin_top": 149,
        "gap_h": 0, "gap_v": 0,
    },
}


def gerar_avery(
    imagens: list[Image.Image],
    template_key: str,
) -> list[Image.Image]:
    t = TEMPLATES_AVERY.get(template_key)
    if t is None:
        return []

    por_folha = t["cols"] * t["rows"]
    folhas    = []

    for i in range(0, max(len(imagens), 1), por_folha):
        folha = Image.new("RGB", (t["page_w"], t["page_h"]), "white")
        lote  = imagens[i:i + por_folha]
        for j, img in enumerate(lote):
            col = j % t["cols"]
            row = j // t["cols"]
            x   = t["margin_left"] + col * (t["cell_w"] + t["gap_h"])
            y   = t["margin_top"]  + row * (t["cell_h"] + t["gap_v"])
            sc  = min(t["cell_w"] / img.width, t["cell_h"] / img.height)
            nw, nh = int(img.width * sc), int(img.height * sc)
            img_s = img.resize((nw, nh), Image.Resampling.LANCZOS)
            px = x + (t["cell_w"] - nw) // 2
            py = y + (t["cell_h"] - nh) // 2
            folha.paste(img_s, (px, py))
        folhas.append(folha)
    return folhas


# ═══════════════════════════════════════════════════════════════
# 23. EXPORTAÇÃO FRENTE E VERSO (DUPLEX)
# ═══════════════════════════════════════════════════════════════

def exportar_pdf_duplex(
    frentes: list[Image.Image],
    versos: list[Image.Image],
    dpi: int = 150,
) -> bytes:
    """Intercala frente/verso: [f1, v1, f2, v2, ...] para impressão duplex."""
    combinado: list[Image.Image] = []
    for f, v in zip(frentes, versos):
        combinado.append(f)
        combinado.append(v)
    # Páginas sobrando (sem verso)
    for f in frentes[len(versos):]:
        combinado.append(f)
        combinado.append(Image.new("RGB", f.size, "white"))
    return exportar_pdf(combinado, dpi)


# ═══════════════════════════════════════════════════════════════
# 24. CACHE PERSISTENTE DE TEMPLATES
# ═══════════════════════════════════════════════════════════════

_CACHE_DIR = ".cache_templates"


def _cache_key(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()[:24]


def salvar_cache_template(file_bytes: bytes, img: Image.Image) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    key = _cache_key(file_bytes)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    with open(os.path.join(_CACHE_DIR, f"{key}.png"), "wb") as f:
        f.write(buf.getvalue())


def carregar_cache_template(
    file_bytes: bytes,
) -> Optional[Image.Image]:
    key  = _cache_key(file_bytes)
    path = os.path.join(_CACHE_DIR, f"{key}.png")
    if os.path.isfile(path):
        return Image.open(path)
    return None


# ═══════════════════════════════════════════════════════════════
# 25. METADADOS DE LOTE (GERAÇÃO INCREMENTAL)
# ═══════════════════════════════════════════════════════════════

_LOTES_DIR = "lotes"


def salvar_metadados_lote(lote_id: str, meta: dict) -> None:
    os.makedirs(_LOTES_DIR, exist_ok=True)
    path = os.path.join(_LOTES_DIR, f"{lote_id}.json")
    meta["atualizado_em"] = datetime.now().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def carregar_metadados_lote(lote_id: str) -> dict:
    path = os.path.join(_LOTES_DIR, f"{lote_id}.json")
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def listar_lotes_salvos() -> list[dict]:
    if not os.path.isdir(_LOTES_DIR):
        return []
    lotes = []
    for nome in sorted(os.listdir(_LOTES_DIR), reverse=True):
        if nome.endswith(".json"):
            try:
                with open(os.path.join(_LOTES_DIR, nome)) as f:
                    d = json.load(f)
                    d["_arquivo"] = nome[:-5]
                    lotes.append(d)
            except Exception:
                pass
    return lotes


# ═══════════════════════════════════════════════════════════════
# 26. WEBHOOK DE NOTIFICAÇÃO
# ═══════════════════════════════════════════════════════════════

import threading as _threading

def disparar_webhook(url: str, payload: dict) -> None:
    """Dispara POST em background thread com retry automático."""
    def _post() -> None:
        try:
            import urllib.request
            import urllib.error
            data = json.dumps(payload).encode()
            req  = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            for tentativa in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=10):
                        break
                except urllib.error.URLError:
                    if tentativa == 2:
                        pass
        except Exception:
            pass
    _threading.Thread(target=_post, daemon=True).start()


# ═══════════════════════════════════════════════════════════════
# 27. GOOGLE SHEETS (requer gspread + service account)
# ═══════════════════════════════════════════════════════════════

def ler_google_sheets(
    sheet_url_ou_id: str,
    creds_json_path: str,
) -> tuple[list[dict], str]:
    """
    Lê uma planilha Google Sheets e retorna lista de dicts.
    Retorna (linhas, mensagem_de_erro).
    A planilha deve ser compartilhada com o e-mail da service account.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return [], "gspread não instalado. Execute: pip install gspread google-auth"

    try:
        scopes  = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds   = Credentials.from_service_account_file(creds_json_path, scopes=scopes)
        cliente = gspread.authorize(creds)
        if "spreadsheets/d/" in sheet_url_ou_id:
            sheet = cliente.open_by_url(sheet_url_ou_id)
        else:
            sheet = cliente.open_by_key(sheet_url_ou_id)
        ws    = sheet.sheet1
        rows  = ws.get_all_records()
        return rows, ""
    except Exception as e:
        return [], f"Erro ao acessar Google Sheets: {e}"


# ═══════════════════════════════════════════════════════════════
# 28. UPLOAD GOOGLE DRIVE / S3
# ═══════════════════════════════════════════════════════════════

def upload_google_drive(
    pdf_bytes: bytes,
    folder_id: str,
    nome_arquivo: str,
    creds_json_path: str,
) -> tuple[str, str]:
    """Retorna (link_compartilhamento, mensagem_de_erro)."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaInMemoryUpload
        from google.oauth2.service_account import Credentials
    except ImportError:
        return "", "google-api-python-client não instalado."

    try:
        creds   = Credentials.from_service_account_file(
            creds_json_path,
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        service = build("drive", "v3", credentials=creds)
        meta    = {"name": nome_arquivo, "parents": [folder_id]}
        media   = MediaInMemoryUpload(pdf_bytes, mimetype="application/pdf")
        arq     = service.files().create(
            body=meta, media_body=media, fields="id"
        ).execute()
        fid     = arq.get("id", "")
        service.permissions().create(
            fileId=fid,
            body={"type": "anyone", "role": "reader"}
        ).execute()
        link = f"https://drive.google.com/file/d/{fid}/view"
        return link, ""
    except Exception as e:
        return "", f"Erro no upload: {e}"


def upload_s3(
    pdf_bytes: bytes,
    bucket: str,
    key: str,
    aws_access_key: str,
    aws_secret_key: str,
    region: str = "us-east-1",
) -> tuple[str, str]:
    """Retorna (url_publica, mensagem_de_erro)."""
    try:
        import boto3
    except ImportError:
        return "", "boto3 não instalado. Execute: pip install boto3"
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region,
        )
        s3.put_object(
            Bucket=bucket, Key=key, Body=pdf_bytes,
            ContentType="application/pdf", ACL="public-read",
        )
        url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
        return url, ""
    except Exception as e:
        return "", f"Erro no upload S3: {e}"


# ═══════════════════════════════════════════════════════════════
# 29. AGENDAMENTO (APScheduler)
# ═══════════════════════════════════════════════════════════════

_scheduler = None
ARQUIVO_AGENDAMENTOS = "agendamentos.json"


def iniciar_scheduler():
    global _scheduler
    if _scheduler is None:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            _scheduler = BackgroundScheduler()
            _scheduler.start()
        except ImportError:
            pass
    return _scheduler


def salvar_agendamento(nome: str, config: dict) -> None:
    ags = carregar_agendamentos()
    ags[nome] = {**config, "criado_em": datetime.now().isoformat()}
    with open(ARQUIVO_AGENDAMENTOS, "w", encoding="utf-8") as f:
        json.dump(ags, f, ensure_ascii=False, indent=2)


def carregar_agendamentos() -> dict:
    if not os.path.isfile(ARQUIVO_AGENDAMENTOS):
        return {}
    try:
        with open(ARQUIVO_AGENDAMENTOS) as f:
            return json.load(f)
    except Exception:
        return {}


def deletar_agendamento(nome: str) -> None:
    ags = carregar_agendamentos()
    ags.pop(nome, None)
    with open(ARQUIVO_AGENDAMENTOS, "w", encoding="utf-8") as f:
        json.dump(ags, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# 30. INTERNACIONALIZAÇÃO (i18n)
# ═══════════════════════════════════════════════════════════════

_traducoes_cache: dict[str, dict] = {}


def carregar_traducoes(pasta: str = "i18n") -> dict[str, dict]:
    global _traducoes_cache
    if _traducoes_cache:
        return _traducoes_cache
    if not os.path.isdir(pasta):
        return {}
    for nome in os.listdir(pasta):
        if nome.endswith(".json"):
            lang = nome[:-5]
            try:
                with open(os.path.join(pasta, nome), encoding="utf-8") as f:
                    _traducoes_cache[lang] = json.load(f)
            except Exception:
                pass
    return _traducoes_cache


def t(chave: str, lang: str = "pt", traducoes: Optional[dict] = None) -> str:
    if traducoes is None:
        traducoes = carregar_traducoes()
    return traducoes.get(lang, {}).get(chave, chave)

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

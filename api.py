"""
api.py — API REST do Gerador de Comandas
Executa em paralelo ao Streamlit: uvicorn api:app --port 8001

Endpoints:
  GET  /health          — status da API
  POST /gerar           — gera PDF e retorna como download
  POST /gerar/zip       — gera ZIP de PNGs individuais
  GET  /url/{numero}    — retorna a URL que seria codificada no QR
"""

import base64
import io

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

import core

app = FastAPI(
    title="Gerador de Comandas — API",
    description="Gera comandas com QR Code ou Código de Barras via REST.",
    version="3.0.0",
)


# ═══════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════

class GerarRequest(BaseModel):
    modo: str = Field("qr", description="'qr' ou 'barcode'")
    inicio: int = Field(1, ge=1)
    fim: int = Field(10, ge=1)
    dpi: int = Field(150, description="72 | 150 | 200 | 300")

    # Template (base64 PNG/JPG obrigatório)
    template_base64: str = Field(..., description="Imagem base64 (PNG ou JPG)")

    # QR Code
    documento: Optional[str] = None
    tipo_doc: str = "CNPJ"
    tamanho_qr: int = 450
    qr_x: int = 540
    qr_y: int = 1035
    fill_color: str = "#000000"
    back_color: str = "#FFFFFF"
    rotacao_qr: int = 0

    # Barcode
    largura: int = 570
    altura: int = 215
    bar_x: int = 535
    bar_y: int = 600
    corte_vertical: int = 27
    corte_esq: int = 8
    corte_dir: int = 8
    rotacao_barra: int = 0

    # Texto/número
    tamanho_texto: int = 150
    texto_x: int = 533
    texto_y: int = 1445
    cor_texto: str = "#000000"
    rotacao_texto: int = 0

    # Fonte
    caminho_fonte: str = Field("fonts/arial.ttf",
                                description="Caminho local para o arquivo .ttf")

    # Grade (opcional)
    grade_ativa: bool = False
    grade_cols: int = 2
    grade_rows: int = 3
    tamanho_pagina: str = "A4 — 150 DPI"
    margem_grade: int = 40
    gap_grade: int = 10


class UrlResponse(BaseModel):
    numero: int
    documento: str
    dado_base: str
    url: str
    base64_payload: str


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def _decode_template(b64: str) -> "Image":
    from PIL import Image
    try:
        img_bytes = base64.b64decode(b64)
        return Image.open(io.BytesIO(img_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"template_base64 inválido: {e}")


def _montar_config(req: GerarRequest, modo_str: str) -> dict:
    if modo_str == "QR Code":
        return {
            "tamanho_qr": req.tamanho_qr,
            "qr_x": req.qr_x, "qr_y": req.qr_y,
            "tamanho_texto": req.tamanho_texto,
            "texto_x": req.texto_x, "texto_y": req.texto_y,
            "cor_texto": req.cor_texto,
            "rotacao_qr": req.rotacao_qr,
            "rotacao_texto": req.rotacao_texto,
            "fill_color": req.fill_color,
            "back_color": req.back_color,
            "caminho_fonte": req.caminho_fonte,
        }
    return {
        "prefixo": "/",
        "largura": req.largura, "altura": req.altura,
        "corte_vertical": req.corte_vertical,
        "corte_esq": req.corte_esq, "corte_dir": req.corte_dir,
        "bar_x": req.bar_x, "bar_y": req.bar_y,
        "tamanho_texto": req.tamanho_texto,
        "texto_x": req.texto_x, "texto_y": req.texto_y,
        "cor_texto": req.cor_texto,
        "rotacao_barra": req.rotacao_barra,
        "rotacao_texto": req.rotacao_texto,
        "caminho_fonte": req.caminho_fonte,
    }


def _gerar_imagens(req: GerarRequest):
    modo_str = "QR Code" if req.modo.lower() in ("qr", "qrcode", "qr code") else "Código de Barras"

    background = _decode_template(req.template_base64)
    config     = _montar_config(req, modo_str)

    dado_base = ""
    if modo_str == "QR Code":
        if not req.documento:
            raise HTTPException(status_code=400,
                                detail="Campo 'documento' obrigatório no modo QR.")
        valido, msg = core.validar_documento(req.documento, req.tipo_doc)
        if not valido:
            raise HTTPException(status_code=422, detail=msg)
        dado_base = core.aplicar_mascara_qrcode(req.documento, req.tipo_doc)

    imgs, falhas = core.gerar_lista_imagens(
        modo_str, background, req.inicio, req.fim, dado_base, config
    )
    if not imgs:
        raise HTTPException(status_code=500, detail=f"Falha na geração. Números: {falhas}")

    if req.grade_ativa:
        pw, ph = core.TAMANHOS_PAGINA.get(req.tamanho_pagina, (1240, 1754))
        imgs_pdf = core.gerar_grade_pagina(
            imgs, req.grade_cols, req.grade_rows, pw, ph,
            req.margem_grade, req.gap_grade,
        )
    else:
        imgs_pdf = imgs

    return imgs_pdf, imgs, dado_base


# ═══════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/health")
def health():
    return {
        "status": "ok",
        "pyzbar": core.PYZBAR_DISPONIVEL,
        "fontes": list(core.carregar_fontes_disponiveis().keys()),
    }


@app.post("/gerar",
          summary="Gera PDF com as comandas",
          response_class=StreamingResponse)
def gerar_pdf(req: GerarRequest):
    imgs_pdf, _, _ = _gerar_imagens(req)
    pdf_bytes = core.exportar_pdf(imgs_pdf, req.dpi)
    filename  = f"comandas_{req.inicio}_{req.fim}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/gerar/zip",
          summary="Gera ZIP com PNGs individuais",
          response_class=StreamingResponse)
def gerar_zip(req: GerarRequest):
    _, imgs_originais, _ = _gerar_imagens(req)
    zip_bytes = core.exportar_zip_pngs(imgs_originais, req.inicio)
    filename  = f"comandas_{req.inicio}_{req.fim}_pngs.zip"
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/url/{numero}",
         summary="Retorna a URL que será codificada no QR",
         response_model=UrlResponse)
def get_url(numero: int, documento: str, tipo: str = "CNPJ"):
    valido, msg = core.validar_documento(documento, tipo)
    if not valido:
        raise HTTPException(status_code=422, detail=msg)
    dado_base = core.aplicar_mascara_qrcode(documento, tipo)
    url = core.gerar_url_qrcode(numero, dado_base)
    texto = f"{dado_base}{numero}"
    b64   = base64.b64encode(texto.encode()).decode()
    return UrlResponse(
        numero=numero,
        documento=documento,
        dado_base=dado_base,
        url=url,
        base64_payload=b64,
    )


@app.post("/validar",
          summary="Valida QR Codes gerados (requer pyzbar)")
def validar(req: GerarRequest):
    if not core.PYZBAR_DISPONIVEL:
        raise HTTPException(status_code=501,
                            detail="pyzbar não instalado. Execute: pip install pyzbar")
    if not req.documento:
        raise HTTPException(status_code=400, detail="'documento' obrigatório.")
    valido, msg = core.validar_documento(req.documento, req.tipo_doc)
    if not valido:
        raise HTTPException(status_code=422, detail=msg)
    dado_base = core.aplicar_mascara_qrcode(req.documento, req.tipo_doc)
    numeros   = list(range(req.inicio, req.fim + 1))
    resultados = core.validar_qrs_em_lote(
        numeros, dado_base, req.fill_color, req.back_color
    )
    total_ok  = sum(1 for r in resultados if r["ok"] is True)
    return JSONResponse({
        "total": len(resultados),
        "validos": total_ok,
        "falhas": len(resultados) - total_ok,
        "detalhes": resultados,
    })

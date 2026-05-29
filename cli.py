"""
cli.py — Interface de linha de comando do Gerador de Comandas

Uso:
  python cli.py gerar --template arte.png --doc 12345678000195 --inicio 1 --fim 100
  python cli.py url --numero 7 --doc 12345678000195
  python cli.py importar-csv --csv lista.csv --template arte.png
  python cli.py calibracao --doc 12345678000195
  python cli.py lotes
"""

import sys
import os
import io

try:
    import click
except ImportError:
    print("❌ click não instalado. Execute: pip install click")
    sys.exit(1)

from PIL import Image
import core


def _carregar_template(template_path: str) -> Image.Image:
    if not os.path.isfile(template_path):
        click.echo(f"❌ Template não encontrado: '{template_path}'", err=True)
        sys.exit(1)
    with open(template_path, "rb") as f:
        return Image.open(io.BytesIO(f.read()))


def _carregar_fonte_padrao() -> str:
    fontes = core.carregar_fontes_disponiveis()
    if not fontes:
        click.echo("❌ Nenhuma fonte encontrada na pasta 'fonts/'.", err=True)
        sys.exit(1)
    return list(fontes.values())[0]


# ─────────────────────────────────────────────────────
@click.group()
@click.version_option("3.0.0", prog_name="gerador-comandas")
def cli():
    """📄 Gerador de Comandas — Interface de Linha de Comando"""


# ─────────────────────────────────────────────────────
@cli.command()
@click.option("--template",   "-t", required=True,   help="Caminho para o template PNG/JPG")
@click.option("--doc",        "-d", default="",       help="CPF ou CNPJ (somente dígitos)")
@click.option("--tipo-doc",         default="CNPJ",   help="CPF ou CNPJ", show_default=True)
@click.option("--inicio",     "-i", default=1,        type=int, help="Número inicial", show_default=True)
@click.option("--fim",        "-f", default=10,       type=int, help="Número final", show_default=True)
@click.option("--lista",      "-l", default="",       help="Lista de números: '1,3,5,10-20' (substitui --inicio/--fim)")
@click.option("--output",     "-o", default="comandas.pdf", help="Arquivo de saída", show_default=True)
@click.option("--dpi",              default=150,      type=int, help="DPI do PDF", show_default=True)
@click.option("--fonte",            default=None,     help="Caminho para fonte .ttf (padrão: primeira em fonts/)")
@click.option("--prefixo",          default="",       help="Prefixo para a série numérica")
@click.option("--sufixo",           default="",       help="Sufixo para a série numérica")
@click.option("--padding",          default=4,        type=int, help="Zeros à esquerda do número", show_default=True)
@click.option("--grade/--no-grade", default=False,    help="Ativar grade de impressão")
@click.option("--grade-cols",       default=2,        type=int, show_default=True)
@click.option("--grade-rows",       default=3,        type=int, show_default=True)
@click.option("--bleed/--no-bleed", default=False,    help="Adicionar marcas de corte")
@click.option("--bleed-px",         default=30,       type=int, show_default=True)
@click.option("--avery",            default="",       help=f"Template Avery: {list(core.TEMPLATES_AVERY.keys())[:2]}...")
@click.option("--token/--no-token", default=False,    help="Gerar QR com token único por comanda")
@click.option("--webhook-url",      default="",       help="URL para notificação após gerar")
@click.option("--zip/--no-zip",     default=False,    help="Gerar também ZIP de PNGs")
@click.option("--modo",             default="qr",     type=click.Choice(["qr","barcode"]), show_default=True)
def gerar(template, doc, tipo_doc, inicio, fim, lista, output, dpi, fonte,
          prefixo, sufixo, padding, grade, grade_cols, grade_rows,
          bleed, bleed_px, avery, token, webhook_url, zip, modo):
    """Gera comandas e exporta como PDF (e opcionalmente ZIP de PNGs)."""

    click.echo(f"📄 Gerador de Comandas CLI v3.0")

    bg     = _carregar_template(template)
    fonte  = fonte or _carregar_fonte_padrao()

    # Intervalo ou lista
    if lista.strip():
        numeros, err = core.parsear_lista_numeros(lista)
        if err:
            click.echo(f"❌ Lista inválida: {err}", err=True); sys.exit(1)
        click.echo(f"📋 Lista: {len(numeros)} números")
    else:
        numeros = list(range(inicio, fim + 1))

    # Documento (QR)
    dado_base = ""
    if modo == "qr":
        if not doc:
            click.echo("❌ --doc é obrigatório no modo QR.", err=True); sys.exit(1)
        ok, msg = core.validar_documento(doc, tipo_doc)
        if not ok:
            click.echo(f"❌ {msg}", err=True); sys.exit(1)
        dado_base = core.aplicar_mascara_qrcode(doc, tipo_doc)

    config = {
        "tamanho_qr": 450, "qr_x": 540, "qr_y": 1035,
        "tamanho_texto": 150, "texto_x": 533, "texto_y": 1445,
        "cor_texto": "#000000", "rotacao_qr": 0, "rotacao_texto": 0,
        "fill_color": "#000000", "back_color": "#FFFFFF",
        "prefixo": "/", "largura": 570, "altura": 215,
        "corte_vertical": 27, "corte_esq": 8, "corte_dir": 8,
        "bar_x": 535, "bar_y": 600,
        "rotacao_barra": 0, "caminho_fonte": fonte,
    }

    # Tokens
    tokens_map: dict[int, str] = {}

    total = len(numeros)
    click.echo(f"⚙️  Gerando {total} comanda(s)… DPI={dpi}")

    with click.progressbar(numeros, label="Progresso") as bar:
        imagens = []
        for n in bar:
            if token and modo == "qr":
                img_qr, tok = core.gerar_qrcode_token(
                    n, dado_base, config["tamanho_qr"],
                    config["fill_color"], config["back_color"],
                )
                tokens_map[n] = tok
                # Compor manualmente com o token QR
                imagem = bg.copy().convert("RGBA")
                draw_tmp = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).ImageDraw.Draw(imagem)
                qw, qh = img_qr.size
                imagem.paste(img_qr, (config["qr_x"]-qw//2, config["qr_y"]-qh//2), img_qr)
                fonte_obj = core.carregar_fonte(fonte, config["tamanho_texto"])
                if fonte_obj:
                    core._colar_texto(draw_tmp, imagem, str(n), fonte_obj,
                                      config["texto_x"], config["texto_y"],
                                      config["cor_texto"], 0)
                img = imagem.convert("RGB")
            elif modo == "qr":
                img = core.gerar_imagem_qrcode(bg, n, dado_base, config)
            else:
                img = core.gerar_imagem_barcode(bg, n, config)

            if img:
                if bleed:
                    img = core.adicionar_marcas_corte(img, bleed_px)
                imagens.append(img)

    if tokens_map:
        tok_file = output.replace(".pdf", "_tokens.json")
        core.salvar_tokens(tokens_map, tok_file)
        click.echo(f"🔑 Tokens salvos em: {tok_file}")

    if not imagens:
        click.echo("❌ Nenhuma imagem gerada.", err=True); sys.exit(1)

    # Grade / Avery
    if avery and avery in core.TEMPLATES_AVERY:
        click.echo(f"🏷️  Montando etiquetas Avery: {avery}")
        imgs_pdf = core.gerar_avery(imagens, avery)
    elif grade:
        pw, ph = core.TAMANHOS_PAGINA.get("A4 — 150 DPI", (1240, 1754))
        click.echo(f"🔲 Montando grade {grade_cols}×{grade_rows}")
        imgs_pdf = core.gerar_grade_pagina(imagens, grade_cols, grade_rows, pw, ph, 40, 10)
    else:
        imgs_pdf = imagens

    # PDF
    pdf_bytes = core.exportar_pdf(imgs_pdf, dpi)
    with open(output, "wb") as f:
        f.write(pdf_bytes)
    click.echo(f"✅ PDF salvo: {output} ({len(pdf_bytes)/1024:.1f} KB)")

    # ZIP
    if zip:
        zip_path = output.replace(".pdf", "_pngs.zip")
        zip_bytes = core.exportar_zip_pngs(imagens, numeros[0])
        with open(zip_path, "wb") as f:
            f.write(zip_bytes)
        click.echo(f"✅ ZIP salvo: {zip_path} ({len(zip_bytes)/1024:.1f} KB)")

    # Auditoria
    h = core.calcular_hash(pdf_bytes)
    core.registrar_auditoria(
        f"{modo.upper()} CLI", doc or "barcode",
        numeros[0], numeros[-1], len(imagens),
        dpi, h, len(pdf_bytes)/1024,
    )

    # Webhook
    if webhook_url:
        core.disparar_webhook(webhook_url, {
            "total": len(imagens), "output": output,
            "hash": h, "dpi": dpi,
        })
        click.echo(f"🔔 Webhook disparado: {webhook_url}")

    click.echo(f"🎉 Concluído! {len(imagens)} comanda(s) → {output}")


# ─────────────────────────────────────────────────────
@cli.command()
@click.option("--numero", "-n", required=True, type=int)
@click.option("--doc",    "-d", required=True)
@click.option("--tipo",         default="CNPJ")
def url(numero, doc, tipo):
    """Exibe a URL que seria codificada no QR Code para um número."""
    ok, msg = core.validar_documento(doc, tipo)
    if not ok:
        click.echo(f"❌ {msg}", err=True); sys.exit(1)
    dado_base = core.aplicar_mascara_qrcode(doc, tipo)
    u = core.gerar_url_qrcode(numero, dado_base)
    import base64 as _b64
    payload = _b64.b64encode(f"{dado_base}{numero}".encode()).decode()
    click.echo(f"Documento  : {dado_base}")
    click.echo(f"Número     : {numero}")
    click.echo(f"Payload B64: {payload}")
    click.echo(f"URL        : {u}")


# ─────────────────────────────────────────────────────
@cli.command("importar-csv")
@click.option("--csv",      "-c", required=True, help="Arquivo CSV")
@click.option("--template", "-t", required=True, help="Template PNG/JPG")
@click.option("--doc",      "-d", default="",    help="Documento padrão (se CSV não tiver coluna 'documento')")
@click.option("--tipo-doc",       default="CNPJ")
@click.option("--output",   "-o", default="comandas_csv.pdf")
@click.option("--dpi",            default=150, type=int)
@click.option("--fonte",          default=None)
def importar_csv(csv, template, doc, tipo_doc, output, dpi, fonte):
    """Gera comandas a partir de um arquivo CSV."""
    bg    = _carregar_template(template)
    fonte = fonte or _carregar_fonte_padrao()

    dado_base = ""
    if doc:
        ok, msg = core.validar_documento(doc, tipo_doc)
        if not ok:
            click.echo(f"❌ {msg}", err=True); sys.exit(1)
        dado_base = core.aplicar_mascara_qrcode(doc, tipo_doc)

    with open(csv, "rb") as f:
        csv_bytes = f.read()

    config = {
        "tamanho_qr": 450, "qr_x": 540, "qr_y": 1035,
        "tamanho_texto": 150, "texto_x": 533, "texto_y": 1445,
        "cor_texto": "#000000", "rotacao_qr": 0, "rotacao_texto": 0,
        "fill_color": "#000000", "back_color": "#FFFFFF",
        "caminho_fonte": fonte,
    }

    clique_barra = click.progressbar(length=100, label="CSV")
    progresso = [0]
    def cb(d, t):
        pct = int(d / t * 100) - progresso[0]
        clique_barra.update(pct)
        progresso[0] += pct

    with clique_barra:
        imgs, erros, meta = core.processar_csv(csv_bytes, bg, config, dado_base, progress_cb=cb)

    if erros:
        click.echo(f"\n⚠️  {len(erros)} erro(s):")
        for e in erros[:5]:
            click.echo(f"   • {e}")

    if not imgs:
        click.echo("❌ Nenhuma imagem gerada.", err=True); sys.exit(1)

    pdf_bytes = core.exportar_pdf(imgs, dpi)
    with open(output, "wb") as f:
        f.write(pdf_bytes)
    click.echo(f"\n✅ {len(imgs)} comanda(s) → {output} ({len(pdf_bytes)/1024:.1f} KB)")


# ─────────────────────────────────────────────────────
@cli.command()
@click.option("--doc",  "-d", required=True)
@click.option("--tipo",       default="CNPJ")
@click.option("--fonte",      default=None)
@click.option("--output","-o",default="calibracao.pdf")
def calibracao(doc, tipo, fonte, output):
    """Gera folha de calibração de impressora com QRs em múltiplos tamanhos."""
    ok, msg = core.validar_documento(doc, tipo)
    if not ok:
        click.echo(f"❌ {msg}", err=True); sys.exit(1)
    fonte  = fonte or _carregar_fonte_padrao()
    db     = core.aplicar_mascara_qrcode(doc, tipo)
    config = {"tamanho_qr": 300, "fill_color": "#000000", "back_color": "#FFFFFF"}
    folha  = core.gerar_folha_calibracao(db, config)
    pdf    = core.exportar_pdf([folha], dpi=150)
    with open(output, "wb") as f:
        f.write(pdf)
    click.echo(f"✅ Folha de calibração salva: {output}")


# ─────────────────────────────────────────────────────
@cli.command()
def lotes():
    """Lista todos os lotes salvos com metadados."""
    ls = core.listar_lotes_salvos()
    if not ls:
        click.echo("Nenhum lote salvo.")
        return
    click.echo(f"{'ID':<24} {'Modo':<14} {'Início':>7} {'Fim':>7} {'Atualizado'}")
    click.echo("-" * 70)
    for l in ls:
        click.echo(f"{l.get('_arquivo','?'):<24} "
                   f"{l.get('modo','?'):<14} "
                   f"{str(l.get('inicio','?')):>7} "
                   f"{str(l.get('fim','?')):>7}  "
                   f"{l.get('atualizado_em','?')[:19]}")


# ─────────────────────────────────────────────────────
@cli.command()
def auditoria():
    """Exibe o log de auditoria."""
    regs = core.ler_auditoria()
    if not regs:
        click.echo("Nenhum registro de auditoria.")
        return
    cabecalho = list(regs[0].keys())
    click.echo("  ".join(f"{c:<18}" for c in cabecalho))
    click.echo("-" * (20 * len(cabecalho)))
    for r in regs[-20:]:
        click.echo("  ".join(f"{str(r.get(c,'')):<18}" for c in cabecalho))


if __name__ == "__main__":
    cli()

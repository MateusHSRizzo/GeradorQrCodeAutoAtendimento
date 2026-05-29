"""
scheduler_runner.py — Executa agendamentos de geração em background.
Execute em paralelo ao Streamlit:
  python scheduler_runner.py
"""
import time, os, io
from datetime import datetime
from PIL import Image
import core

def executar_agendamento(nome: str, cfg: dict) -> None:
    print(f"[{datetime.now():%H:%M:%S}] Executando agendamento '{nome}'…")
    fontes = core.carregar_fontes_disponiveis()
    if not fontes:
        print("  ❌ Nenhuma fonte encontrada em fonts/"); return

    template_path = cfg.get("template", "")
    if not os.path.isfile(template_path):
        print(f"  ❌ Template não encontrado: {template_path}"); return

    with open(template_path, "rb") as f:
        bg = Image.open(io.BytesIO(f.read()))

    modo       = cfg.get("modo", "QR Code")
    documento  = cfg.get("documento", "")
    tipo_doc   = cfg.get("tipo_doc", "CNPJ")
    inicio     = int(cfg.get("inicio", 1))
    fim        = int(cfg.get("fim", 10))
    dpi        = int(cfg.get("dpi", 150))
    output     = cfg.get("output", f"agendado_{nome.replace(' ','_')}_{datetime.now():%Y%m%d_%H%M}.pdf")
    cam_fonte  = list(fontes.values())[0]

    dado_base = ""
    if modo == "QR Code" and documento:
        ok, msg = core.validar_documento(documento, tipo_doc)
        if not ok: print(f"  ❌ {msg}"); return
        dado_base = core.aplicar_mascara_qrcode(documento, tipo_doc)

    config = {
        "tamanho_qr": 450, "qr_x": 540, "qr_y": 1035,
        "tamanho_texto": 150, "texto_x": 533, "texto_y": 1445,
        "cor_texto": "#000000", "rotacao_qr": 0, "rotacao_texto": 0,
        "fill_color": "#000000", "back_color": "#FFFFFF",
        "prefixo": "/", "largura": 570, "altura": 215,
        "corte_vertical": 27, "corte_esq": 8, "corte_dir": 8,
        "bar_x": 535, "bar_y": 600, "rotacao_barra": 0,
        "caminho_fonte": cam_fonte,
    }

    imgs, falhas = core.gerar_lista_imagens(modo, bg, inicio, fim, dado_base, config)
    if not imgs: print(f"  ❌ Nenhuma imagem gerada. Falhas: {falhas}"); return

    pdf = core.exportar_pdf(imgs, dpi)
    with open(output, "wb") as f:
        f.write(pdf)

    h = core.calcular_hash(pdf)
    core.registrar_auditoria(f"{modo} (agend.)", documento, inicio, fim,
                              len(imgs), dpi, h, len(pdf)/1024)

    webhook = cfg.get("webhook_url", "")
    if webhook:
        core.disparar_webhook(webhook, {"agendamento": nome, "output": output,
                                         "total": len(imgs), "hash": h})
    print(f"  ✅ {len(imgs)} comandas → {output} ({len(pdf)/1024:.1f} KB)")


def main() -> None:
    print(f"🕐 Scheduler iniciado — {datetime.now():%Y-%m-%d %H:%M:%S}")
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        print("❌ APScheduler não instalado: pip install APScheduler"); return

    sched = BlockingScheduler(timezone="America/Sao_Paulo")
    agendamentos = core.carregar_agendamentos()

    if not agendamentos:
        print("Nenhum agendamento configurado. Crie via app.py → aba Ferramentas.")
        return

    for nome, cfg in agendamentos.items():
        hora_str = cfg.get("hora", "08:00")
        try:
            hora, minuto = map(int, hora_str.split(":"))
        except ValueError:
            print(f"  ⚠️ Hora inválida '{hora_str}' para '{nome}' — ignorado."); continue

        sched.add_job(executar_agendamento, "cron",
                      hour=hora, minute=minuto,
                      args=[nome, cfg], id=nome)
        print(f"  ✅ '{nome}' agendado para {hora_str} todos os dias")

    print("Aguardando horários… (Ctrl+C para parar)")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler encerrado.")


if __name__ == "__main__":
    main()

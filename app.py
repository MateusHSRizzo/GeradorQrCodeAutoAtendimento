"""
app.py — Interface Streamlit do Gerador de Comandas v3.0
"""
import io
import json
import os

import streamlit as st
from PIL import Image

import core

st.set_page_config(page_title="Gerador de Comandas", page_icon="📄",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  .stProgress > div > div > div > div { background-color: #2b83ff; }
  .stTabs [data-baseweb="tab-list"] { gap: 8px; }
  .stTabs [data-baseweb="tab"] { padding: 6px 18px; border-radius: 6px; }
  [data-testid="stSidebar"] { min-width: 330px; max-width: 380px; }
</style>
""", unsafe_allow_html=True)

# ── Session State ──────────────────────────────────────────
if "historico"          not in st.session_state: st.session_state["historico"] = []
if "resultado_val"      not in st.session_state: st.session_state["resultado_val"] = []
if "pdf_gerado"         not in st.session_state: st.session_state["pdf_gerado"] = None
if "zip_gerado"         not in st.session_state: st.session_state["zip_gerado"] = None
if "imgs_geradas"       not in st.session_state: st.session_state["imgs_geradas"] = []

# ── Cache helpers ──────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _img_base(b: bytes) -> Image.Image:
    return Image.open(io.BytesIO(b))

@st.cache_data(show_spinner=False)
def _fontes() -> dict:
    return core.carregar_fontes_disponiveis()

# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
st.sidebar.title("📄 Gerador de Comandas")
st.sidebar.caption("v3.0")

modo = st.sidebar.radio("Modo", ["QR Code", "Código de Barras"],
                         key="modo_selecao", horizontal=True)
pfx = "qr" if modo == "QR Code" else "bc"
fontes_disp = _fontes()

# 1. Ficheiros
with st.sidebar.expander("📁 1. Ficheiros e Fonte", expanded=True):
    img_up = st.file_uploader("Template", type=["png","jpg","jpeg"],
                               key=f"{pfx}_uploader")
    fonte_sel = (st.selectbox("Fonte", sorted(fontes_disp.keys()), key=f"{pfx}_font")
                 if fontes_disp else None)
    if not fontes_disp:
        st.error("Pasta 'fonts/' vazia ou não encontrada.")

background: Image.Image | None = None
max_w, max_h = 2000, 2000
if img_up:
    fb = img_up.read()
    background = _img_base(fb)
    max_w, max_h = background.size
    st.sidebar.caption(f"📐 {max_w}×{max_h} px")

# 2. Intervalo
with st.sidebar.expander("🔢 2. Intervalo", expanded=True):
    c1, c2 = st.columns(2)
    inicio = int(c1.number_input("Inicial", 1, 99999, 1,  1, key=f"{pfx}_inicio"))
    fim    = int(c2.number_input("Final",   1, 99999, 10, 1, key=f"{pfx}_fim"))
    fim    = max(fim, inicio)
    total_c = fim - inicio + 1
    st.caption(f"Total: **{total_c}** comanda(s)")
    if total_c > 500:
        st.warning(f"⚠️ Lote grande ({total_c}). Pode demorar.")

# 3. Documento (QR)
dado_base = ""
documento_str = ""
doc_valido = False
tipo_doc = "CNPJ"
if modo == "QR Code":
    with st.sidebar.expander("📋 3. Documento", expanded=True):
        tipo_doc = st.selectbox("Tipo", ["CNPJ","CPF"], key="qr_tipo_doc")
        documento_str = st.text_input("Documento (só números)",
                                       placeholder="Ex: 12345678000195",
                                       key="qr_doc")
        if documento_str:
            doc_valido, msg_doc = core.validar_documento(documento_str, tipo_doc)
            if doc_valido:
                st.success("✅ Válido")
                dado_base = core.aplicar_mascara_qrcode(documento_str, tipo_doc)
            else:
                st.error(f"❌ {msg_doc}")

# 4. Layout
with st.sidebar.expander("📐 4. Layout", expanded=True):
    if modo == "QR Code":
        tamanho_qr = st.slider("Tamanho QR (px)",50, max(50,max_w), min(450,max_w),10, key="qr_tam_qr")
        tam_txt    = st.slider("Tamanho Nº (pt)",10, max(10,max_h//2), min(150,max(10,max_h//2)),5, key="qr_tam_txt")
        cor_txt    = st.color_picker("Cor Nº","#000000", key="qr_cor")
        c1,c2=st.columns(2)
        qr_x  =c1.number_input("QR X", 0,max_w, min(540,max_w),5,key="qr_x")
        qr_y  =c2.number_input("QR Y", 0,max_h, min(1035,max_h),5,key="qr_y")
        txt_x =c1.number_input("Nº X", 0,max_w, min(533,max_w),5,key="qr_txt_x")
        txt_y =c2.number_input("Nº Y", 0,max_h, min(1445,max_h),5,key="qr_txt_y")
        rot_qr =st.selectbox("Rot. QR (°)",[0,90,180,270],key="qr_rot_qr")
        rot_txt=st.selectbox("Rot. Nº (°)",[0,90,180,270],key="qr_rot_txt")
        bar_x=bar_y=larg_bar=alt_bar=corte_v=corte_e=corte_d=rot_bar=0
    else:
        larg_bar=st.slider("Largura (px)",100,max(100,max_w), min(570,max_w),10,key="bc_largura")
        alt_bar =st.slider("Altura (px)", 50,max(50,max_h//2), min(215,max(50,max_h//2)),5,key="bc_altura")
        tam_txt =st.slider("Tamanho Nº (pt)",10,max(10,max_h//2), min(142,max(10,max_h//2)),2,key="bc_tam_txt")
        cor_txt =st.color_picker("Cor Nº","#FFFFFF",key="bc_cor")
        c1,c2=st.columns(2)
        bar_x=c1.number_input("Barra X",0,max_w, min(535,max_w),5,key="bc_x")
        bar_y=c2.number_input("Barra Y",0,max_h, min(600,max_h),5,key="bc_y")
        txt_x=c1.number_input("Nº X",  0,max_w, min(535,max_w),5,key="bc_txt_x")
        txt_y=c2.number_input("Nº Y",  0,max_h, min(845,max_h),5,key="bc_txt_y")
        corte_v=st.slider("Corte V (%)",0,100,27,1,key="bc_corte_v")
        c3,c4=st.columns(2)
        corte_e=c3.slider("Esq (%)",0,40,8,1,key="bc_corte_e")
        corte_d=c4.slider("Dir (%)",0,40,8,1,key="bc_corte_d")
        rot_bar=st.selectbox("Rot. Barra (°)",[0,90,180,270],key="bc_rot_bar")
        rot_txt=st.selectbox("Rot. Nº (°)",  [0,90,180,270],key="bc_rot_txt")
        tamanho_qr=qr_x=qr_y=rot_qr=0
        fill_color,back_color="#000000","#FFFFFF"

# 5. Avançado
with st.sidebar.expander("🎨 5. Opções Avançadas", expanded=False):
    st.markdown("**Marca d'água**")
    logo_up = st.file_uploader("Logo (PNG)", type=["png"], key="logo_up")
    wm_logo: Image.Image | None = None
    if logo_up:
        wm_logo = Image.open(io.BytesIO(logo_up.read()))
        cw1,cw2=st.columns(2)
        wm_pos=cw1.selectbox("Posição",core.ANCORAS_WATERMARK,index=8,key="wm_pos")
        wm_esc=cw2.slider("Escala (%)",5,50,15,1,key="wm_esc")
        wm_opa=st.slider("Opacidade (%)",10,100,70,5,key="wm_opa")
    else:
        wm_pos,wm_esc,wm_opa="bottom-right",15,70

    if modo == "QR Code":
        st.markdown("**Cores do QR**")
        cq1,cq2=st.columns(2)
        fill_color=cq1.color_picker("Frente","#000000",key="qr_fill")
        back_color=cq2.color_picker("Fundo", "#FFFFFF",key="qr_back")
        ratio=core.calcular_contraste_wcag(fill_color,back_color)
        label=("✅ AAA" if ratio>=7 else "✅ AA" if ratio>=4.5
               else "⚠️ AA+" if ratio>=3 else "❌ Ilegível")
        st.caption(f"Contraste WCAG: **{ratio:.1f}:1** {label}")
    else:
        fill_color,back_color="#000000","#FFFFFF"

# 6. Grade
with st.sidebar.expander("🔲 6. Grade de Impressão", expanded=False):
    grade_ativa=st.checkbox("Ativar grade",key="grade_ativa")
    if grade_ativa:
        cg1,cg2=st.columns(2)
        grade_cols=int(cg1.number_input("Colunas",1,10,2,1,key="grade_cols"))
        grade_rows=int(cg2.number_input("Linhas", 1,10,3,1,key="grade_rows"))
        tam_pag=st.selectbox("Tamanho pág.",list(core.TAMANHOS_PAGINA.keys()),key="grade_pag")
        margem_g=st.slider("Margem (px)",10,100,40,5,key="grade_margem")
        gap_g   =st.slider("Espaço (px)", 0,50, 10,2,key="grade_gap")
        por_pag=grade_cols*grade_rows
        st.caption(f"{por_pag}/pág → ~{-(-total_c//por_pag)} página(s)")
    else:
        grade_cols=grade_rows=1; tam_pag="A4 — 150 DPI"; margem_g=gap_g=0

# 7. Exportação
with st.sidebar.expander("⬇️ 7. Exportação", expanded=False):
    dpi=st.selectbox("DPI",[72,150,200,300],index=1,key="dpi")
    mostrar_reg=st.checkbox("Réguas e guias",value=True,key="reguas")
    fazer_val=st.checkbox(
        "Validar QRs após gerar"+(
            " ✅" if core.PYZBAR_DISPONIVEL else " ⚠️(pyzbar ausente)"),
        value=core.PYZBAR_DISPONIVEL, key="fazer_val",
        disabled=not core.PYZBAR_DISPONIVEL)

# 8. Perfis
with st.sidebar.expander("💾 8. Perfis de Configuração", expanded=False):
    perfis=core.carregar_perfis()
    if perfis:
        psel=st.selectbox("Carregar",["— selecionar —"]+sorted(perfis.keys()),
                           key="psel")
        if psel!="— selecionar —":
            cp1,cp2=st.columns(2)
            if cp1.button("📥 Carregar",key="btn_load_p",use_container_width=True):
                for k,v in perfis[psel]["config"].items():
                    st.session_state[k]=v
                st.success(f"'{psel}' carregado!"); st.rerun()
            if cp2.button("🗑️ Deletar",key="btn_del_p",use_container_width=True):
                core.deletar_perfil(psel)
                st.success(f"'{psel}' removido."); st.rerun()
    else:
        st.caption("Nenhum perfil salvo.")
    nome_p=st.text_input("Nome do perfil",key="nome_perfil")
    if st.button("💾 Salvar perfil",key="btn_save_p",use_container_width=True):
        if not nome_p.strip():
            st.error("Digite um nome.")
        else:
            cfg_salvar={"modo_selecao":modo,f"{pfx}_inicio":inicio,
                        f"{pfx}_fim":fim,"dpi":dpi,"grade_ativa":grade_ativa}
            if modo=="QR Code":
                cfg_salvar.update({"qr_tipo_doc":tipo_doc,"qr_doc":documento_str,
                    "qr_tam_qr":tamanho_qr,"qr_tam_txt":tam_txt,"qr_cor":cor_txt,
                    "qr_x":qr_x,"qr_y":qr_y,"qr_txt_x":txt_x,"qr_txt_y":txt_y,
                    "qr_rot_qr":rot_qr,"qr_rot_txt":rot_txt,
                    "qr_fill":fill_color,"qr_back":back_color})
            else:
                cfg_salvar.update({"bc_largura":larg_bar,"bc_altura":alt_bar,
                    "bc_tam_txt":tam_txt,"bc_cor":cor_txt,
                    "bc_x":bar_x,"bc_y":bar_y,"bc_txt_x":txt_x,"bc_txt_y":txt_y,
                    "bc_corte_v":corte_v,"bc_corte_e":corte_e,"bc_corte_d":corte_d,
                    "bc_rot_bar":rot_bar,"bc_rot_txt":rot_txt})
            core.salvar_perfil(nome_p.strip(),cfg_salvar)
            st.success(f"'{nome_p.strip()}' salvo!"); st.rerun()

# ── Config objects ─────────────────────────────────────────
caminho_fonte=fontes_disp.get(fonte_sel,"") if fonte_sel else ""

if modo=="QR Code":
    config_atual={
        "tamanho_qr":tamanho_qr,"qr_x":qr_x,"qr_y":qr_y,
        "tamanho_texto":tam_txt,"texto_x":txt_x,"texto_y":txt_y,
        "cor_texto":cor_txt,"rotacao_qr":rot_qr,"rotacao_texto":rot_txt,
        "fill_color":fill_color,"back_color":back_color,
        "caminho_fonte":caminho_fonte}
else:
    config_atual={
        "prefixo":"/","largura":larg_bar,"altura":alt_bar,
        "corte_vertical":corte_v,"corte_esq":corte_e,"corte_dir":corte_d,
        "bar_x":bar_x,"bar_y":bar_y,
        "tamanho_texto":tam_txt,"texto_x":txt_x,"texto_y":txt_y,
        "cor_texto":cor_txt,"rotacao_barra":rot_bar,"rotacao_texto":rot_txt,
        "caminho_fonte":caminho_fonte}

wm_config=({"logo":wm_logo,"posicao":wm_pos,"escala":wm_esc,"opacidade":wm_opa}
           if wm_logo else None)

# ══════════════════════════════════════════════════════════════
# TÍTULO
# ══════════════════════════════════════════════════════════════
st.title("📄 Gerador de Comandas")
if background:
    st.caption(f"Template: **{max_w}×{max_h}px** | Modo: **{modo}** | Lote: **{inicio}→{fim}** ({total_c} comandas)")

# ══════════════════════════════════════════════════════════════
# ABAS
# ══════════════════════════════════════════════════════════════
tab_prev, tab_grade_prev, tab_csv, tab_hist = st.tabs([
    "🖼️ Preview Unitário",
    "🔲 Preview em Grade",
    "📋 Importar CSV",
    "📊 Histórico & Auditoria",
])

# ── ABA 1: Preview Unitário ────────────────────────────────
with tab_prev:
    prereqs_ok = (background and fonte_sel and
                  (modo != "QR Code" or doc_valido))
    if not prereqs_ok:
        st.info("Preencha o template, fonte" +
                (" e documento" if modo=="QR Code" else "") +
                " na barra lateral.")
    else:
        num_pv = st.slider("Número para preview",inicio,fim,inicio,1,key="num_pv")
        col_img, col_info = st.columns([3,1])

        with st.spinner("Gerando preview…"):
            img_pv = (core.gerar_imagem_qrcode(background,num_pv,dado_base,config_atual,wm_config)
                      if modo=="QR Code"
                      else core.gerar_imagem_barcode(background,num_pv,config_atual,wm_config))

        with col_img:
            if img_pv:
                if mostrar_reg:
                    guias=({"Código":{"x":qr_x,"y":qr_y,"color":"#ff4b4b"},
                             "Número":{"x":txt_x,"y":txt_y,"color":"#2b83ff"}}
                           if modo=="QR Code"
                           else {"Código":{"x":bar_x,"y":bar_y,"color":"#ff4b4b"},
                                 "Número":{"x":txt_x,"y":txt_y,"color":"#2b83ff"}})
                    st.image(core.draw_rulers_and_guides(img_pv,guias),
                             caption=f"Comanda Nº {num_pv}",use_container_width=True)
                else:
                    st.image(img_pv,caption=f"Comanda Nº {num_pv}",use_container_width=True)

        with col_info:
            st.markdown("**Info**")
            if modo=="QR Code":
                st.metric("QR",f"{tamanho_qr}×{tamanho_qr}px")
                st.metric("Pos. QR",f"({qr_x},{qr_y})")
                r=core.calcular_contraste_wcag(fill_color,back_color)
                st.metric("Contraste WCAG",f"{r:.1f}:1")
                st.markdown("**URL:**")
                st.code(core.gerar_url_qrcode(num_pv,dado_base),language=None)
            else:
                st.metric("Barra",f"{larg_bar}×{alt_bar}px")
                st.metric("Pos.",f"({bar_x},{bar_y})")
            st.metric("Pos. Nº",f"({txt_x},{txt_y})")
            if img_pv:
                st.markdown("---")
                st.markdown("**P&B (impressão)**")
                img_pb=core.simular_escala_cinza(img_pv)
                st.image(img_pb,use_container_width=True)
                cm=core.calcular_contraste_michelson(img_pv)
                lbl=("✅ Bom" if cm>=0.7 else "⚠️ Médio" if cm>=0.4 else "❌ Baixo")
                st.caption(f"Contraste: {cm:.2f} {lbl}")

# ── ABA 2: Preview em Grade ────────────────────────────────
with tab_grade_prev:
    prereqs_g = (background and fonte_sel and
                 (modo!="QR Code" or doc_valido))
    if not prereqs_g:
        st.info("Preencha os campos obrigatórios na barra lateral.")
    else:
        import math as _math
        n_g=st.selectbox("Amostras na grade",[4,6,9],index=0,key="n_g")
        if st.button("🔄 Gerar Preview em Grade",key="btn_gp",use_container_width=True):
            cols_g=int(_math.ceil(_math.sqrt(n_g)))
            rows_g=int(_math.ceil(n_g/cols_g))
            step=max(1,(fim-inicio)//(n_g-1)) if n_g>1 else 1
            ids=sorted(set([inicio]+list(range(inicio,fim+1,step))+[fim]))[:n_g]
            bar_g=st.progress(0,"Gerando amostras…")
            ams=[]
            for i,n in enumerate(ids):
                img_a=(core.gerar_imagem_qrcode(background,n,dado_base,config_atual,wm_config)
                       if modo=="QR Code"
                       else core.gerar_imagem_barcode(background,n,config_atual,wm_config))
                if img_a: ams.append(img_a)
                bar_g.progress((i+1)/len(ids),f"Amostra {i+1}/{len(ids)}")
            bar_g.empty()
            if ams:
                pw,ph=core.TAMANHOS_PAGINA.get(
                    st.session_state.get("grade_pag","A4 — 150 DPI"),(1240,1754))
                pgs=core.gerar_grade_pagina(ams,cols_g,rows_g,pw,ph,40,10)
                if pgs:
                    st.image(pgs[0],
                             caption=f"Grade {cols_g}×{rows_g} — nums: {ids}",
                             use_container_width=True)

# ── ABA 3: CSV ────────────────────────────────────────────
with tab_csv:
    st.subheader("📋 Importar Lista via CSV")
    st.markdown("""
Colunas suportadas:
- **`numero`** *(obrigatório)* — número da comanda
- **`documento`** *(opcional)* — substitui o documento global (CPF/CNPJ por linha)
- **`nome`** *(opcional)* — registrado no log de auditoria
""")
    tmpl="numero,documento,nome\n1,12345678000195,Mesa 1\n2,,Mesa 2\n3,12345678901,José"
    st.download_button("⬇️ Baixar template CSV",tmpl.encode(),
                        "template.csv","text/csv")
    csv_up=st.file_uploader("Arquivo CSV",type=["csv"],key="csv_up")
    if csv_up:
        import csv as _csv
        cb=csv_up.read()
        rows_p=list(_csv.DictReader(io.StringIO(cb.decode("utf-8-sig",errors="replace"))))
        if rows_p:
            st.caption(f"**{len(rows_p)} linhas** — primeiras 5:")
            st.dataframe(rows_p[:5],use_container_width=True,hide_index=True)
        if not background:
            st.warning("Faça upload do template na barra lateral.")
        elif modo!="QR Code":
            st.warning("Importação CSV disponível somente no modo QR Code.")
        elif not fonte_sel:
            st.warning("Selecione uma fonte.")
        else:
            t_csv=st.checkbox("Aceito os termos de responsabilidade.",key="t_csv")
            if st.button("⚙️ Gerar do CSV",type="primary",
                          use_container_width=True,disabled=not t_csv,key="btn_csv"):
                pb_csv=st.progress(0,"Processando CSV…")
                def _cb_csv(d,t): pb_csv.progress(d/t,f"Gerando… {d}/{t}")
                imgs_c,errs_c,meta_c=core.processar_csv(
                    cb,background,config_atual,dado_base,wm_config,_cb_csv)
                pb_csv.empty()
                if errs_c:
                    st.warning(f"{len(errs_c)} erro(s):")
                    for e in errs_c[:10]: st.caption(f"• {e}")
                if imgs_c:
                    st.success(f"✅ {len(imgs_c)} comanda(s) gerada(s)!")
                    imgs_pdf_c=(core.gerar_grade_pagina(imgs_c,grade_cols,grade_rows,
                        *core.TAMANHOS_PAGINA.get(tam_pag,(1240,1754)),margem_g,gap_g)
                        if grade_ativa else imgs_c)
                    pdf_c=core.exportar_pdf(imgs_pdf_c,dpi)
                    zip_c=core.exportar_zip_pngs(imgs_c,1)
                    cc1,cc2=st.columns(2)
                    cc1.download_button("⬇️ PDF (CSV)",pdf_c,"comandas_csv.pdf",
                                         "application/pdf",use_container_width=True)
                    cc2.download_button("⬇️ PNGs ZIP",zip_c,"comandas_csv.zip",
                                         "application/zip",use_container_width=True)
                    h=core.calcular_hash(pdf_c)
                    core.registrar_auditoria(f"{modo} (CSV)","múltiplos",0,
                        len(imgs_c)-1,len(imgs_c),dpi,h,len(pdf_c)/1024)
                    if meta_c:
                        st.dataframe(meta_c,use_container_width=True,hide_index=True)

# ── ABA 4: Histórico & Auditoria ─────────────────────────
with tab_hist:
    ch1,ch2=st.columns(2)
    with ch1:
        st.subheader("📋 Histórico da Sessão")
        hist=st.session_state["historico"]
        if not hist:
            st.info("Nenhuma geração nesta sessão.")
        else:
            for i,e in enumerate(reversed(hist)):
                with st.expander(f"#{len(hist)-i} | {e['timestamp']} | {e['modo']} | {e['inicio']}→{e['fim']}",
                                  expanded=(i==0)):
                    ci1,ci2,ci3=st.columns(3)
                    ci1.metric("Total",e["total"])
                    ci2.metric("DPI",e["dpi"])
                    ci3.metric("Tamanho",f"{e['tamanho_kb']:.1f}KB")
                    st.caption(f"Hash: `{e['hash']}` | Doc: {e['documento']}")
                    if e.get("pdf_bytes"):
                        st.download_button("⬇️ Re-baixar PDF",e["pdf_bytes"],
                            f"comandas_{e['inicio']}_{e['fim']}.pdf",
                            "application/pdf",key=f"rdl_{i}",use_container_width=True)
    with ch2:
        st.subheader("📊 Log de Auditoria")
        regs=core.ler_auditoria()
        if not regs:
            st.info("Nenhum registro. Logs criados após cada geração.")
        else:
            st.dataframe(regs,use_container_width=True,hide_index=True)
            import csv as _csv2
            cbuf=io.StringIO()
            _csv2.DictWriter(cbuf,fieldnames=regs[0].keys()).writeheader()
            _csv2.DictWriter(cbuf,fieldnames=regs[0].keys()).writerows(regs)
            st.download_button("⬇️ Exportar Log",cbuf.getvalue().encode(),
                                "audit_log.csv","text/csv",use_container_width=True)
        if st.button("🗑️ Limpar log",key="btn_clr"):
            if os.path.isfile(core.ARQUIVO_AUDITORIA):
                os.remove(core.ARQUIVO_AUDITORIA); st.rerun()

        # Resultados de validação QR
        val_res=st.session_state.get("resultado_val",[])
        if val_res:
            st.subheader("🔍 Última Validação de QR")
            for r in val_res:
                icon=("✅" if r["ok"] else "❌" if r["ok"] is False else "❓")
                st.caption(f"{icon} **#{r['numero']}** → `{r['url_lida'][:70]}`")

# ══════════════════════════════════════════════════════════════
# BLOCO DE GERAÇÃO (sempre visível)
# ══════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("⚙️ Gerar e Exportar")

erros_pre=[]
if not background:         erros_pre.append("template")
if not fonte_sel:          erros_pre.append("fonte")
if modo=="QR Code" and not doc_valido: erros_pre.append("documento válido")
if erros_pre:
    st.warning("⚠️ Pendente: " + " | ".join(erros_pre))

st.warning("**⚠️ Atenção:** Teste e valide as comandas antes de usar em produção.")
termos=st.checkbox("Li e aceito os termos de responsabilidade.",key="termos_main")

if st.button("⚙️ Gerar Comandas",type="primary",use_container_width=True,
              key="btn_gerar",disabled=not(termos and not erros_pre)):

    # ── Geração paralela
    bar_main=st.progress(0,"Gerando…")
    def _cb(d,t): bar_main.progress(d/t,f"Gerando… {d}/{t}")
    lista_imgs,falhas=core.gerar_lista_imagens(
        modo,background,inicio,fim,dado_base,config_atual,wm_config,_cb)
    bar_main.empty()

    if falhas: st.warning(f"⚠️ Falha nos nºs: {falhas}")
    if not lista_imgs: st.error("Nenhuma imagem gerada."); st.stop()
    st.success(f"✅ {len(lista_imgs)} comanda(s) gerada(s)!")

    # ── Grade (se ativa)
    if grade_ativa:
        with st.spinner("Montando grade…"):
            pw,ph=core.TAMANHOS_PAGINA.get(tam_pag,(1240,1754))
            imgs_pdf=core.gerar_grade_pagina(lista_imgs,grade_cols,grade_rows,
                                              pw,ph,margem_g,gap_g)
        st.info(f"Grade {grade_cols}×{grade_rows} → {len(imgs_pdf)} página(s)")
    else:
        imgs_pdf=lista_imgs

    # ── Exportação
    with st.spinner("Compilando PDF…"):
        pdf_bytes=core.exportar_pdf(imgs_pdf,dpi)
    with st.spinner("Compactando PNGs…"):
        zip_bytes=core.exportar_zip_pngs(lista_imgs,inicio)

    st.session_state.update({
        "pdf_gerado":pdf_bytes,"zip_gerado":zip_bytes,"imgs_geradas":lista_imgs})

    cd1,cd2=st.columns(2)
    cd1.download_button("⬇️ Baixar PDF",pdf_bytes,
        f"comandas_{inicio}_a_{fim}.pdf","application/pdf",use_container_width=True)
    cd2.download_button("⬇️ Baixar PNGs (.zip)",zip_bytes,
        f"comandas_{inicio}_a_{fim}_pngs.zip","application/zip",use_container_width=True)
    st.caption(f"PDF: {len(pdf_bytes)/1024:.1f}KB | ZIP: {len(zip_bytes)/1024:.1f}KB | DPI: {dpi}"
               +(f" | Grade {grade_cols}×{grade_rows}" if grade_ativa else ""))

    # ── Auditoria
    h=core.calcular_hash(pdf_bytes)
    core.registrar_auditoria(modo,documento_str or "barcode",inicio,fim,
                              len(lista_imgs),dpi,h,len(pdf_bytes)/1024)
    import datetime as _dt
    st.session_state["historico"].append({
        "timestamp":_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "modo":modo,"documento":documento_str or "—",
        "inicio":inicio,"fim":fim,"total":len(lista_imgs),
        "dpi":dpi,"hash":h,"tamanho_kb":len(pdf_bytes)/1024,
        "pdf_bytes":pdf_bytes})

    # ── Validação QR
    if modo=="QR Code" and fazer_val and core.PYZBAR_DISPONIVEL:
        with st.spinner("Validando QR Codes…"):
            amostra=[int(x) for x in set(
                [inicio]+list(range(inicio,fim+1,max(1,(fim-inicio)//9)))+[fim])][:10]
            rv=core.validar_qrs_em_lote(amostra,dado_base,fill_color,back_color)
        st.session_state["resultado_val"]=rv
        ok_n=sum(1 for r in rv if r["ok"] is True)
        err_n=sum(1 for r in rv if r["ok"] is False)
        cv1,cv2=st.columns(2)
        cv1.success(f"✅ {ok_n}/{len(rv)} QRs válidos")
        if err_n: cv2.error(f"❌ {err_n} falha(s)")
        with st.expander("Ver detalhes"):
            for r in rv:
                ic=("✅" if r["ok"] else "❌" if r["ok"] is False else "❓")
                st.caption(f"{ic} **#{r['numero']}** → `{r['url_lida'][:70]}`")

    # ── E-mail
    st.markdown("---")
    st.subheader("📧 Enviar PDF por E-mail")
    smtp_ok=all([os.environ.get("EMAIL_HOST"),
                 os.environ.get("EMAIL_USER"),
                 os.environ.get("EMAIL_PASS")])
    if not smtp_ok:
        st.info("Configure `.env` com EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASS para usar este recurso.")
    else:
        ce1,ce2,ce3=st.columns([2,2,1])
        dest=ce1.text_input("Destinatário",placeholder="email@exemplo.com",key="e_dest")
        assunto_e=ce2.text_input("Assunto",
                                   value=f"Comandas {inicio}→{fim}",key="e_assunto")
        if ce3.button("📤 Enviar",key="btn_email",
                       use_container_width=True,disabled=not dest):
            with st.spinner("Enviando…"):
                ok_m,msg_m=core.enviar_email(dest,pdf_bytes,
                    f"comandas_{inicio}_{fim}.pdf",assunto_e)
            if ok_m: st.success(msg_m)
            else:    st.error(msg_m)

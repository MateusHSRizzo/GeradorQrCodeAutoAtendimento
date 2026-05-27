# 📄 Gerador de Comandas — v3.0

Gera automaticamente comandas com **QR Code** ou **Código de Barras (Code39)**
a partir de um template de imagem. Exporta como PDF, ZIP de PNGs individuais,
ou consome via **API REST**.

---

## 🚀 Início rápido

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# Ubuntu/Debian — para validação de QR com pyzbar (opcional)
sudo apt-get install libzbar0

# 2. (Opcional) Configurar e-mail
cp .env.example .env
# edite .env com suas credenciais SMTP

# 3. Rodar o app Streamlit
streamlit run app.py

# 4. (Opcional) Rodar a API REST em paralelo
uvicorn api:app --port 8001 --reload
# Documentação automática: http://localhost:8001/docs
```

---

## 📁 Estrutura do projeto

```
.
├── app.py            # Interface Streamlit (UI completa)
├── core.py           # Lógica central (reutilizável)
├── api.py            # API REST FastAPI
├── requirements.txt
├── .env.example      # Template de credenciais SMTP
├── README.md
├── fonts/            # Fontes TTF (obrigatório)
│   └── *.ttf
├── profiles.json     # Perfis salvos (auto-gerado)
└── audit_log.csv     # Log de auditoria (auto-gerado)
```

---

## ✨ Funcionalidades — v3.0

### Interface (app.py)

| Aba | O que faz |
|-----|-----------|
| 🖼️ **Preview Unitário** | Preview com réguas, simulação P&B, métricas, URL gerada |
| 🔲 **Preview em Grade** | Miniatura de N×M amostras antes de gerar o lote |
| 📋 **Importar CSV** | Gera uma comanda por linha com documento por linha |
| 📊 **Histórico & Auditoria** | Lotes da sessão com re-download + log CSV |

### Sidebar — todas as opções

| Seção | Recursos |
|-------|----------|
| 📁 Ficheiros | Template PNG/JPG + seletor de fonte TTF |
| 🔢 Intervalo | Início/fim + alerta de lote grande (>500) |
| 📋 Documento | CPF / CNPJ com validação em tempo real |
| 📐 Layout | X/Y, tamanhos, rotações para código e número |
| 🎨 Avançado | **Marca d'água** (posição, escala, opacidade) + **Cores do QR** (frente/fundo) com medidor WCAG |
| 🔲 Grade | Cols×Rows por página, tamanho A4/A5/Carta, margem, gap |
| ⬇️ Exportação | DPI 72/150/200/300, réguas, toggle de validação pyzbar |
| 💾 Perfis | Salvar, carregar e deletar configurações nomeadas |

### Core (core.py)

- Geração paralela com `ThreadPoolExecutor` (até 8 threads)
- Cache de QR codes com `lru_cache` (mesmos params = sem reprocessamento)
- Validação de QR via `pyzbar` (decodifica e compara URL)
- Contraste WCAG entre cores (ratio e classificação AA/AAA)
- Simulação de impressão P&B + contraste Michelson
- Grade de impressão (N×M por página A4/A5/Carta)
- Watermark com 9 posições de ancoragem e opacidade
- Importação via CSV (documento por linha)
- Envio por e-mail via SMTP (SSL e STARTTLS)
- Log de auditoria (CSV com hash SHA-256 do PDF)
- Perfis de configuração em JSON local

---

## 🌐 API REST (api.py)

```bash
uvicorn api:app --port 8001
```

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/health` | Status, pyzbar e fontes disponíveis |
| POST | `/gerar` | Gera e retorna PDF |
| POST | `/gerar/zip` | Gera e retorna ZIP de PNGs |
| GET | `/url/{numero}` | Retorna URL/base64 que seria gerada |
| POST | `/validar` | Valida QRs gerados (requer pyzbar) |

**Documentação interativa:** http://localhost:8001/docs

Exemplo de chamada:
```bash
curl -X POST http://localhost:8001/gerar \
  -H "Content-Type: application/json" \
  -d '{
    "modo": "qr",
    "inicio": 1, "fim": 10,
    "documento": "12345678000195",
    "tipo_doc": "CNPJ",
    "template_base64": "<base64_do_template>",
    "dpi": 150
  }' --output comandas.pdf
```

---

## 🔗 Lógica de URL (preservada)

```
texto   = "{CPF_ou_CNPJ_formatado}:{numero}"
base64  = base64_encode(texto)
url     = "https://pediucomeu.com.br/autoatendimento/{base64}"
```

---

## 📧 Configuração de E-mail

Crie um arquivo `.env` na raiz do projeto:

```env
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=seu@email.com
EMAIL_PASS=sua_senha_de_app
```

> **Gmail:** use uma [Senha de App](https://myaccount.google.com/apppasswords),
> não sua senha normal.

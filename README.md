# 📄 Gerador de Comandas — v4.0

Sistema completo para geração de comandas com **QR Code** ou **Código de Barras (Code39)**.
Interface Streamlit, API REST, CLI e agendamento automático.

---

## 🚀 Início rápido

```bash
pip install -r requirements.txt
# Ubuntu/Debian (para validação QR):
sudo apt-get install libzbar0

streamlit run app.py                      # Interface principal
uvicorn api:app --port 8001               # API REST (paralelo)
python cli.py gerar --help                # CLI
python scheduler_runner.py               # Agendamento automático
```

---

## 📁 Estrutura

```
.
├── app.py                  # Interface Streamlit v4.0
├── core.py                 # Lógica central (1 500 linhas, 50+ funções)
├── api.py                  # API REST FastAPI
├── cli.py                  # Interface de linha de comando
├── scheduler_runner.py     # Runner de agendamentos recorrentes
├── requirements.txt
├── .env.example            # Credenciais SMTP
├── auth_config.yaml.example# Configuração de multi-usuário
├── i18n/
│   ├── pt.json             # Português
│   ├── en.json             # English
│   └── es.json             # Español
├── fonts/                  # Fontes TTF (obrigatório)
├── profiles.json           # Perfis salvos (auto-gerado)
├── audit_log.csv           # Log de auditoria (auto-gerado)
├── agendamentos.json       # Agendamentos (auto-gerado)
└── lotes/                  # Metadados de lotes (auto-gerado)
```

---

## ✨ Todos os recursos — v4.0

### 🎨 Editor Visual
| Recurso | Descrição |
|---------|-----------|
| Preview unitário interativo | Slider para qualquer número do intervalo + simulação P&B |
| QR Code com logo embutido | Logo no centro do QR (nível H de correção de erros) |
| Campos variáveis extras | Até 3 textos extras por comanda com posição independente |
| Numeração não-sequencial | Aceita expressão `1,3,5,10-20,50` em vez de só intervalo |
| Preview de frente e verso | Upload de template do verso para PDF duplex |

### 🔗 Integrações
| Recurso | Descrição |
|---------|-----------|
| Google Sheets | Lê colunas `numero/documento/nome` diretamente da planilha |
| Google Drive | Upload automático do PDF após geração |
| Amazon S3 | Upload automático com URL pública |
| Webhook | POST com metadados do lote ao concluir (3 retentativas) |
| Agendamento (APScheduler) | Geração recorrente diária sem abrir o app |

### 🛡️ Segurança & Rastreabilidade
| Recurso | Descrição |
|---------|-----------|
| Assinatura digital | Stub pronto para pyhanko + certificado X.509 |
| Token único por comanda | UUID embutido na URL — impossibilita reutilização |
| Série / prefixo / sufixo | `TURNO-A-0001` a `TURNO-A-0100` |
| Log de auditoria | CSV com SHA-256 do PDF, usuário, timestamp |

### 🖨️ Impressão Profissional
| Recurso | Descrição |
|---------|-----------|
| Marcas de corte / sangria | Cropmarks + área de bleed para gráficas |
| Folha de calibração | QRs em 5 tamanhos + régua 150mm |
| Etiquetas Avery | 5160, 5163, 5167, L7160 prontas |
| PDF Duplex (frente e verso) | Intercalação automática `f1,v1,f2,v2…` |

### ⚡ Performance & Automação
| Recurso | Descrição |
|---------|-----------|
| CLI completo | `gerar`, `url`, `importar-csv`, `calibracao`, `lotes`, `auditoria` |
| Cache persistente de templates | Salvo em `.cache_templates/` — evita re-abertura |
| Geração incremental | Metadados em `lotes/` para retomar lotes parciais |
| Multi-usuário | streamlit-authenticator + `auth_config.yaml` |
| Internacionalização | PT 🇧🇷 / EN 🇺🇸 / ES 🇪🇸 via `i18n/*.json` |

---

## 💻 CLI

```bash
# Gerar 100 comandas
python cli.py gerar \
  --template arte.png \
  --doc 12345678000195 \
  --inicio 1 --fim 100 \
  --output comandas.pdf \
  --dpi 150

# Lista de números personalizada
python cli.py gerar \
  --template arte.png --doc 12345678000195 \
  --lista "1,3,5,10-20,50" --output especial.pdf

# Com grade 2×3 e marcas de corte
python cli.py gerar \
  --template arte.png --doc 12345678000195 \
  --inicio 1 --fim 60 --grade --grade-cols 2 --grade-rows 3 --bleed

# Com token único + ZIP
python cli.py gerar \
  --template arte.png --doc 12345678000195 \
  --inicio 1 --fim 50 --token --zip

# Etiquetas Avery
python cli.py gerar \
  --template arte.png --doc 12345678000195 \
  --inicio 1 --fim 30 \
  --avery "Avery 5160 — 3×10 (2,625\"×1\")"

# Ver URL de um número
python cli.py url --numero 7 --doc 12345678000195

# Importar CSV
python cli.py importar-csv \
  --csv lista.csv --template arte.png

# Folha de calibração
python cli.py calibracao --doc 12345678000195

# Listar lotes salvos
python cli.py lotes

# Ver log de auditoria
python cli.py auditoria
```

---

## 🌐 API REST

```bash
uvicorn api:app --port 8001
# Swagger: http://localhost:8001/docs
```

| Endpoint | Descrição |
|----------|-----------|
| `GET /health` | Status, pyzbar, fontes disponíveis |
| `POST /gerar` | Retorna PDF |
| `POST /gerar/zip` | Retorna ZIP de PNGs |
| `GET /url/{numero}` | URL + base64 do QR |
| `POST /validar` | Valida QRs com pyzbar |

---

## 🔐 Multi-usuário

```bash
# Gerar hash de senha
python -c "import streamlit_authenticator as sa; print(sa.Hasher(['senha']).generate())"

# Copiar e editar
cp auth_config.yaml.example auth_config.yaml
```

---

## ⏰ Agendamento automático

1. Configure agendamentos no app → aba **Ferramentas → Agendamento**
2. Execute em background:
```bash
python scheduler_runner.py
```

---

## 📧 E-mail

```env
# .env
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=seu@email.com
EMAIL_PASS=senha_de_app
```

---

## ☁️ Integrações de nuvem

```env
# Google Drive / Sheets — credentials.json via Google Cloud Console
# Amazon S3
AWS_ACCESS_KEY_ID=sua_chave
AWS_SECRET_ACCESS_KEY=sua_chave_secreta
```

---

## 🔗 Lógica de URL (preservada integralmente)

```
texto   = "{DOCUMENTO_FORMATADO}:{numero}"
base64  = base64_encode(texto)
url     = "https://pediucomeu.com.br/autoatendimento/{base64}"

# Com token único:
url     = "https://pediucomeu.com.br/autoatendimento/{base64}?t={token_uuid}"
```

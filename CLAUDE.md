# D-PPG Manager - Vasoquant 1000

**Autor**: Dr. Alexandre Amato — Instituto Amato de Medicina Avançada
**Site**: software.amato.com.br

Aplicativo para leitura, análise e geração de laudos de fotopletismografia digital (D-PPG)
a partir do aparelho Elcat Vasoquant 1000. O software original só funciona em Windows antigo.
Este projeto cria uma alternativa completa em Python para Mac/Linux/Windows.

## Aplicativos

| App | Arquivo | Descrição |
|-----|---------|-----------|
| **D-PPG Manager** | `dppg_manager.py` | App principal: pacientes, exames, laudos, PDF |
| **D-PPG Reader** | `dppg_reader.py` | App legado standalone (GUI simples, sem banco) |

### Executar (Desenvolvimento)
```bash
python3 dppg_manager.py
```

### Executável Standalone
```bash
# macOS
pyinstaller dppg_manager.spec --clean --noconfirm
open "dist/DPPG Manager.app"

# Windows
build_windows.bat
```

O executável (.app / .exe) é standalone (~88MB), não precisa de Python instalado.
Banco de dados fica em `~/Documents/DPPG Manager/dppg_manager.db`.

## Estrutura do Projeto

```
dppg/
├── dppg_manager.py            # Entry point do D-PPG Manager
├── dppg_manager.spec           # PyInstaller build spec (macOS + Windows)
├── build_windows.bat           # Script de build para Windows
├── requirements.txt            # Dependências: numpy, scipy, matplotlib, reportlab, sqlalchemy
├── dppg.icns / dppg.ico        # Ícones do app (macOS / Windows)
│
├── src/                        # Código-fonte modular
│   ├── __init__.py
│   ├── config.py               # Constantes: sampling rate, thresholds, labels
│   ├── models.py               # PPGParameters (To,Th,Ti,Vo,Fo,τ), PPGBlock
│   ├── analysis.py             # Cálculo de parâmetros, τ, assimetria, efeito garrote
│   ├── protocol.py             # Parser do protocolo serial binário
│   ├── exporters.py            # Exportação CSV/JSON
│   │
│   ├── db/                     # Banco de dados SQLite (SQLAlchemy)
│   │   ├── schema.py           # Tabelas: Patient, Exam, ExamChannel, Settings
│   │   └── operations.py       # CRUD operations
│   │
│   ├── capture/                # Captura de dados do hardware
│   │   ├── connection.py       # Conexão TCP ao conversor serial-WiFi
│   │   └── receiver.py         # Recepção e parsing de dados em tempo real
│   │
│   ├── diagnosis/              # Diagnóstico automático
│   │   ├── classifier.py       # Classificação por graus (Normal, I, II, III)
│   │   └── text_generator.py   # Geração de texto diagnóstico em português
│   │
│   ├── gui/                    # Interface gráfica (tkinter)
│   │   ├── app.py              # Janela principal, menu bar, navegação
│   │   ├── patient_list.py     # Lista de pacientes com busca
│   │   ├── patient_form.py     # Formulário de cadastro de paciente
│   │   ├── capture_view.py     # Tela de captura de dados do hardware
│   │   ├── exam_view.py        # Visualização de exame (4 gráficos + parâmetros)
│   │   ├── report_editor.py    # Editor de laudo (queixas + diagnóstico + PDF)
│   │   ├── settings_view.py    # Configurações (clínica, médico, CRM)
│   │   └── widgets.py          # Widgets: PPGCanvas, DiagnosticChart,
│   │                           #   ParametersTable, AdvancedAnalysisPanel
│   │
│   └── report/                 # Geração de laudo PDF
│       ├── templates.py        # Constantes de layout, cores, textos
│       ├── chart_renderer.py   # Renderização matplotlib→PNG (PPG, diagnóstico, radar)
│       └── pdf_generator.py    # Geração do PDF A4 com reportlab
│
├── scripts/                    # Scripts utilitários
│   ├── analyze_exam.py         # Análise detalhada de exames capturados
│   ├── serial_sniffer.py       # Sniffer serial para debug do protocolo
│   ├── parse_raw_capture.py    # Parser de capturas brutas
│   └── sniffer_windows.bat     # Launcher do sniffer para Windows
│
├── docs/                       # Documentação de engenharia reversa
│   ├── DLL_ANALYSIS_REPORT.md  # Relatório de análise da dppg 2.dll
│   ├── DLL_DISASSEMBLY_FINDINGS.md  # Achados do disassembly
│   ├── PARAMETROS_CALCULO.md   # Parâmetros de cálculo detalhados
│   ├── TI_EXTRAPOLATION_ANALYSIS.md  # Análise da extrapolação Ti
│   ├── CAPTURA_SERIAL_WINDOWS.md  # Guia de captura serial no Windows
│   └── SNIFFER_WINDOWS.md      # Documentação do sniffer Windows
│
├── dppg_reader.py              # App legado (standalone, duplica src/)
├── CLAUDE.md                   # Esta documentação
├── PROTOCOL.md                 # Documentação detalhada do protocolo (v2.0)
├── README.md                   # Documentação pública do projeto
├── LICENSE                     # MIT License
│
├── laudos/                     # Laudos oficiais para validação (gitignored)
└── app_original/               # Software original Vasoview (gitignored)
    └── redist/
        ├── dppg 2.dll          # DLL com algoritmos (analisada via radare2)
        ├── vl320hw.dll         # DLL de comunicação serial (analisada)
        └── ELCmain 2.exe       # Executável principal
```

## Funcionalidades do D-PPG Manager

### Gerenciamento de Pacientes
- Cadastro com nome, nascimento, sexo, ID, convênio
- Busca em tempo real na lista de pacientes
- Múltiplos exames por paciente

### Captura de Dados
- Conexão TCP ao conversor serial-WiFi (WS1C)
- Recepção automática de exames exportados do Vasoquant
- Protocolo DLE/ACK (emulação de impressora)
- Parsing de metadados do hardware (baseline, peak, endpoint)

### Análise de Parâmetros
6 parâmetros clássicos + 3 análises avançadas:

| Parâmetro | Descrição | Unidade | Fonte |
|-----------|-----------|---------|-------|
| **To** | Venous refilling time | s | VASOSCREEN |
| **Th** | Half-amplitude time | s | VASOSCREEN |
| **Ti** | Initial inflow time (extrapolação linear adaptativa) | s | VASOSCREEN |
| **Vo** | Venous pump power | % | VASOSCREEN |
| **Fo** | Venous pump capacity (integral da curva) | %·s | VASOSCREEN |
| **τ (tau)** | Constante de tempo exponencial (curve_fit) | s | **Novo** |

Análises avançadas (não existem no VASOSCREEN original):

| Análise | Descrição | Implementação |
|---------|-----------|---------------|
| **Índice de assimetria bilateral** | Compara MIE vs MID para To, Vo, τ | `bilateral_asymmetry()` em analysis.py |
| **Efeito do garrote quantificado** | % de mudança no To/Vo com tourniquet | `tourniquet_effect()` em analysis.py |
| **Constante de tempo τ** | Fit exponencial `y(t) = A·exp(-t/τ) + C` | `_calculate_tau()` em analysis.py |

### Visualização
- 4 gráficos PPG (MIE/MID × com/sem garrote) com marcadores de pico e endpoint
- Gráfico diagnóstico Vo% × To(s) com zonas coloridas (normal/borderline/abnormal)
- Tabela de parâmetros com coloração (vermelho = anormal, ciano = normal)
- Painel de análise avançada (assimetria + efeito do garrote)

### Geração de Laudo PDF
Laudo A4 em página única contendo:
- Header com clínica, médico, CRM
- Dados do paciente
- 4 gráficos PPG (2×2)
- Tabela de parâmetros (To, Th, Ti, Vo, Fo, τ)
- Gráfico diagnóstico Vo% × To(s) (scatter com zonas)
- **Radar chart bilateral** (comparação MIE vs MID - spider chart)
- Tabela de classificação (Normal, Grau I/II/III)
- Análise avançada (assimetria + efeito garrote %)
- Texto de queixas e diagnóstico (gerado automaticamente em português)
- Assinatura do médico
- Bibliografia

### Menu do App
- **Editar > Configurações**: Clínica, médico, CRM, títulos do laudo
- **Ajuda > Sobre**: Versão, autor, instituto

## Dependências

```
numpy>=1.20          # Arrays e cálculos numéricos
scipy>=1.7           # curve_fit para τ (constante de tempo exponencial)
matplotlib>=3.5      # Renderização de gráficos (backend Agg → PNG)
reportlab>=4.0       # Geração de PDF
sqlalchemy>=2.0      # ORM para banco de dados SQLite
```

Para build: `pyinstaller>=6.0`

## Hardware

### Aparelho
- **Modelo**: Elcat Vasoquant 1000 D-PPG
- **Interface original**: Porta serial RS-232
- **Baud rate**: 9600 (configurável: 4800 ou 9600)
- **Configuração**: 8N2 (8 data bits, No parity, **2 stop bits**)
- **Controle de fluxo**: Nenhum
- **Buffers**: RX 1024, TX 256 bytes
- **Fonte**: Disassembly de vl320hw.dll (DCB.StopBits = 2 em 0x10011658)

### Conversor Serial-WiFi
- **Modelo**: TGY Cyber WS1C
- **Documentação**: https://www.tgycyber.com/pt-BR/docs/ws1c
- **IP configurado**: 192.168.0.234
- **Porta TCP**: 1100 (padrão para Serial 1)

## Protocolo de Comunicação

**IMPORTANTE**: O `vl320hw.dll` suporta dois dispositivos com protocolos DISTINTOS:
- **VQ1000** (serial RS-232): Protocolo **binário ESC** (comandos `1B xx`)
- **VL320** (USB Vasolab): Protocolo **ASCII** (TST:CHECK, ACQ:START, etc.)

Os comandos ASCII (TST:CHECK, ACQ:START) são **exclusivos do VL320** e causam
desconexão imediata se enviados ao VQ1000.

### Modo 1: Emulação de Impressora (DLE/ACK) - Padrão

Protocolo baseado em impressora serial (modo padrão):

1. Aparelho envia **DLE (0x10)** periodicamente para verificar se "impressora" está online
2. Resposta completa do Vasoview: **ACK+ESC+'I' (0x06 0x1B 0x49)** — 3 bytes
3. Aparelho responde com 13 bytes de identificação (SOH + tipo + serial + firmware + EOT + CR)
4. Se não respondermos, aparelho mostra "printer offline"

**Nota**: Nosso app envia apenas ACK (1 byte) e funciona para receber dados exportados.
O handshake completo (3 bytes) é usado pelo Vasoview para entrar em modo de comando.

### Modo 2: Comandos Binários ESC (Modo Comando do VQ1000)

Protocolo binário nativo para controle programático do VQ1000:

| Comando | Bytes | Descrição |
|---------|-------|-----------|
| Handshake | `06 1B 49` | Resposta ao DLE + solicitação de ID |
| Get config | `1B 4B 3F` | Consultar configuração |
| Get directory | `1B 55 3F` | Listar exames na memória |
| Start meas | `1B 4D xx` | Iniciar medição (canal xx) |
| Stop | `1B 41` | Parar aquisição |
| Get data | `1B 4C xx xx` | Buscar exame (16-bit LE) |
| Disconnect | `1B 44` | Desconectar |
| Keep-alive | `1B 6B` | Manter conexão remota |

**Keep-alive binário**: SYN (0x16) ou ENQ (0x05), timeout de 4 segundos.

### Formato dos Dados

Quando o usuário exporta um exame, o aparelho envia:

```
1B           = ESC (início de bloco)
4C E2 04     = Label "Lâ" + EOT (identificador do canal/medição)
01           = SOH (Start of Header)
1D 00 FA 00  = GS + tamanho (0x00FA = 250 amostras)
[dados]      = Amostras PPG de 16 bits little-endian
[metadados]  = Informações adicionais no final
```

### Valores PPG
- Formato: 16 bits little-endian (low byte primeiro)
- Faixa típica: 2000-3500 (ADC de 12 bits)
- Taxa de amostragem: **4 Hz** (confirmado: 64 amostras em 16 segundos de exercício)
- Conversão ADC → %PPG: ~27 unidades ADC = 1% PPG

### Caracteres de Controle Reconhecidos
- **0x10 (DLE)**: Data Link Escape - polling de status (~1x/segundo)
- **0x06 (ACK)**: Acknowledge - resposta de "pronto" (nós enviamos)
- **0x04 (EOT)**: End of Transmission - fim de bloco de dados
- **0x05 (ENQ)**: Enquiry
- **0x01 (SOH)**: Start of Header - início de bloco de dados
- **0x1B (ESC)**: Escape - início de comando/label
- **0x1D (GS)**: Group Separator - header com tamanho

### Formato dos Metadados (após amostras)

Decodificado via análise empírica de 32 blocos verificados contra laudos oficiais.
O hardware envia parâmetros pré-calculados junto com os dados:

```
Byte 0:      0x1D (GS marker)
Bytes 1-2:   baseline (16-bit LE, ADC units)
Bytes 3-5:   00 00 00 (separator)
Byte 6:      0x1D (GS marker)
Bytes 7-8:   exam_number (16-bit LE)
--- PAYLOAD (parâmetros calculados pelo hardware) ---
Byte 9:      To_samples (end_index - peak_index, em amostras)
Byte 10:     Th_samples (amostras até 50% recuperação do pico)
Bytes 11-12: amplitude (16-bit LE, peak_value - baseline, ADC units)
Bytes 13-14: Fo × 100 (16-bit LE, em 0.01 %·s)
Byte 15:     peak_raw (peak_index = peak_raw + 2×sr - 1 = peak_raw + 7)
Byte 16:     Ti (segundos, inteiro)
Byte 17:     flags (0x00=normal, 0x80=endpoint não detectado)
Byte 18:     0x04 (EOT)
```

**Valores derivados:**
- `peak_index = peak_raw + 7` (ajuste de 2×sr - 1, com sr=4)
- `end_index = peak_index + To_samples`
- `peak_value = baseline + amplitude`
- `To = To_samples / sr` (segundos)
- `Th = Th_samples / sr` (segundos)
- `Vo = amplitude × 100 / baseline` (%)
- `Fo = (payload[4] | payload[5]<<8) / 100` (%·s)

**Verificação**: baseline + amplitude = samples[peak_index] para 32/32 blocos (100%).

### Fluxo do Protocolo (Modo Impressora)
1. Vasoquant envia DLE (0x10) periodicamente para verificar impressora
2. App responde com ACK (0x06) → aparelho mostra "printer online"
   - Vasoview original envia ACK+ESC+I (3 bytes) e recebe 13 bytes de ID
3. Usuário exporta exame no Vasoquant
4. Vasoquant envia: ESC + Label + EOT + SOH + GS + tamanho + dados + metadados
5. App deve responder ACK após receber dados (pacote terminando em 00 04)
6. Vasoquant volta a enviar DLE para polling

### Labels dos Canais
| Label | Byte | Descrição |
|-------|------|-----------|
| Lâ | 0xE2 | MID c/ Tq - Membro Inferior Direito, com Tourniquet |
| Lá | 0xE1 | MID s/ Tq - Membro Inferior Direito, sem Tourniquet |
| Là | 0xE0 | MIE c/ Tq - Membro Inferior Esquerdo, com Tourniquet |
| Lß | 0xDF | MIE s/ Tq - Membro Inferior Esquerdo, sem Tourniquet |

### Configurações de Conexão Padrão
- **IP**: 192.168.0.234
- **Porta**: 1100
- **Auto-ACK**: Ativado
- **Polling**: Passivo (recomendado, baseado na análise do Vasoview)
- **Socket Timeout**: 3 segundos
- **TCP Keep-Alive**: Habilitado (5s no macOS)

## Banco de Dados

SQLite via SQLAlchemy. Tabelas:

| Tabela | Campos principais |
|--------|-------------------|
| **patients** | id, last_name, first_name, date_of_birth, gender, id_number, insurance |
| **exams** | id, patient_id, exam_date, complaints, diagnosis_text |
| **exam_channels** | id, exam_id, label_byte, samples_blob (zlib), hw_* (metadados), To/Th/Ti/Vo/Fo |
| **settings** | key, value (clinic_name, doctor_name, doctor_crm, etc.) |

Localização do banco:
- **Desenvolvimento**: `./dppg_manager.db` (raiz do projeto)
- **Executável (.app/.exe)**: `~/Documents/DPPG Manager/dppg_manager.db`

## Fórmulas dos Parâmetros

### Engenharia Reversa da DLL

Análise completa da biblioteca `dppg 2.dll` via disassembly com radare2.
Função principal: `fcn.100182c0` (1150 bytes). Todos os cálculos usam **aritmética inteira**.

```python
# Baseline: pré-calculado pelo hardware (não pela DLL)
baseline = valor_do_hardware

# Pico e endpoint: pré-calculados pelo hardware
peak_index = peak_raw + 2*sr - 1  # ajustado
end_index  = peak_index + To_samples_do_hardware

# ===== To (Venous Refilling Time) =====
To = round((end_index - peak_index) / sampling_rate)  # segundos

# ===== Th (Half-Amplitude Time) =====
half_amplitude = trunc_div(peak_value - baseline, 2)   # sar eax, 1
for i in range(peak, sample_count):
    if samples[i] - baseline < half_amplitude:
        Th_samples = i - peak
        break
Th = round(Th_samples * 10 / sampling_rate)  # décimos de segundo

# ===== Vo (Venous Pump Power) =====
Vo = (peak_value - baseline) * 1000 / baseline  # décimos de %

# ===== Ti (Initial Inflow Time) — EXTRAPOLAÇÃO LINEAR ADAPTATIVA =====
delta_3sec = peak_value - samples[peak + 3 * sr]
if delta_3sec >= 10:    # limiar = 10 unidades ADC
    window = 3          # decaimento rápido
else:
    window = 6          # decaimento lento
target = peak + window * sr
drop = peak_value - samples[target]
Ti = round(window * (peak_value - baseline) / drop)  # clamped a 120s

# ===== Fo (Venous Pump Capacity) — INTEGRAL DA CURVA =====
area = sum(samples[i] - baseline for i in range(peak, end))
rect_half = (samples[end-1] - baseline) * (end - peak) / 2
Fo = (area - rect_half) * 1000 / baseline / sampling_rate

# ===== τ (Exponential Time Constant) — NOVO, NÃO EXISTE NO VASOSCREEN =====
# Fit: y(t) = A * exp(-t/τ) + C via scipy.optimize.curve_fit
# Aplicado à curva de recuperação (peak → endpoint)
# τ > 0.5s e < 200s; None se fit falhar
```

### Constantes REAIS do Cálculo (aritmética inteira)

| Valor | Endereço | Uso Confirmado |
|-------|----------|----------------|
| `sar eax,1` (÷2) | 0x100183AF | Threshold Th = 50% |
| `0x64` (100) | 0x100183EB | Th: amostras→centissegundos |
| `0x3E8` (1000) | 0x10018425 | Vo: multiplicador para 0.1% |
| `0x0A` (10) | 0x1001848D | Ti: limiar adaptativo (ADC) |
| `0x1E` (30) / `0x3C` (60) | 0x10018494-97 | Ti: janela rápida/lenta |
| `0x78` (120) | 0x10018510 | Ti: máximo (120s) |
| `0x3E8` (1000) | 0x100185E3 | Fo: normalização |
| `sar eax,2` (÷4) | 0x100185F2 | Fo: divisão por sr |

### Constantes que são de IMPRESSÃO (NÃO de cálculo)

As constantes float `0.125`, `0.50`, `3.0`, `100.0`, etc. são **todas de layout de impressão**,
não de análise de sinal. Detalhes em `app_original_v2/PSEUDOCODE_DPPG.md`.

## Diagnóstico Automático

### Classificação por Graus (VASOSCREEN)

| To | Classificação |
|----|---------------|
| > 25s | Normal |
| 20-25s | Grau I |
| 10-20s | Grau II |
| < 10s | Grau III (severa) |

| Vo | Bomba Muscular |
|----|----------------|
| ≥ 3% | Normal (adequada) |
| < 3% | Patológica |

### Interpretação do Garrote
- **Melhora** (To ↑ >15%): Refluxo em sistema venoso superficial
- **Piora** (To ↓ >15%): Insuficiência venosa profunda
- **Sem alteração**: Normal ou componente misto

### Assimetria Bilateral
- `> 20%`: Significativa
- `> 40%`: Muito significativa

## Precisão dos Cálculos

Validado com 19 canais de 4 pacientes contra laudos VASOSCREEN oficiais.

| Parâmetro | Erro Médio | Erro Mediano | Status |
|-----------|------------|--------------|--------|
| **Vo** | 6.1% | 1.0% | Excelente |
| **To** | 20.6% | 7.5% | Bom |
| **Th** | 19.5% | 8.0% | Bom |
| **Ti** | 15.6% | 11.8% | Bom (extrapolação adaptativa) |
| **Fo** | 26.3% | 10.1% | Bom (integral trapezoidal) |
| **Global** | 18.8% | **9.1%** | Mediana < 10% |

### Limitações Conhecidas
1. **Sinais de baixa amplitude (Vo < 3%)**: Erros maiores por SNR desfavorável
2. **Baseline**: Mediana dos primeiros 10 samples quando hardware não fornece
3. **Endpoint (To)**: Threshold crossing a 3% quando hardware não fornece markers

## Formatos de Exportação

### CSV
```csv
block,exam_number,label,sample_index,value
0,1250,Lâ,0,2471
```

### JSON
```json
{
  "export_timestamp": "2026-01-14T15:44:09",
  "sampling_rate_hz": 4.0,
  "blocks": [{
    "label": "Lâ",
    "label_desc": "MID c/ Tq",
    "exam_number": 1250,
    "samples": [...],
    "parameters": {
      "To_s": 28.0, "Th_s": 5.8, "Ti_s": 24, "Vo_percent": 5.9,
      "Fo_percent_s": 62, "tau_s": 15.0
    }
  }]
}
```

## Análise do Vasoview Original

### Via API Monitor (captura Windows)
- **Timeouts infinitos**: Vasoview usa `MAXDWORD` (0xFFFFFFFF)
- **Modo passivo**: Não faz polling ativo — apenas espera e responde
- **Porta**: COM2

### Via Disassembly de vl320hw.dll
- **Aplicação PE32** (Qt4): ELCmain → eCommon.dll → vl320hw.dll → serial
- **Serial thread** (0x100127c0): Loop principal de comunicação
- **Máquina de estados** (0x100118c0): Estados 1-10+, processa byte a byte
- **DLE handshake**: ACK+ESC+I (3 bytes), recebe 13 bytes de ID
- **8N2**: 2 stop bits confirmado
- **Keep-alive**: SYN (0x16) ou ENQ (0x05), timeout 4s
- **Dois protocolos**: VQ1000 = binário ESC, VL320 = ASCII

### Endereços-chave (vl320hw.dll, base 0x10000000)
- `0x10011520`: Serial port open (8N2)
- `0x100127C0`: VQ1000 serial thread
- `0x100118C0`: Byte processing state machine
- `0x10016D00-3F`: Protocol constants
- `0x10013540`: VQ1000_StartAcq
- `0x10012D30`: VQ1000_GetDeviceConfig

## TODO

- [x] Parsear protocolo, identificar canais, extrair metadados
- [x] Calcular parâmetros (To, Th, Ti, Vo, Fo) — validado com 4 pacientes
- [x] Gráfico diagnóstico Vo% × To(s)
- [x] Engenharia reversa completa de dppg 2.dll e vl320hw.dll
- [x] Corrigir Ti (extrapolação linear) e Fo (integral trapezoidal)
- [x] Decodificar metadados do hardware (32/32 verificados)
- [x] Separar protocolos VQ1000 vs VL320
- [x] D-PPG Manager com banco de dados, pacientes, laudos
- [x] Geração de laudo PDF (página única, estilo VASOSCREEN)
- [x] Constante de tempo exponencial τ (curve_fit)
- [x] Índice de assimetria bilateral (MIE vs MID)
- [x] Efeito do garrote quantificado (%)
- [x] Radar chart bilateral no laudo PDF
- [x] Executável standalone (PyInstaller, macOS .app + Windows .exe)
- [x] Ícone do app e janela Sobre
- [ ] Testar handshake estendido ACK+ESC+I com hardware real
- [ ] Implementar modo de comando binário ESC do VQ1000
- [ ] Melhorar detecção de pico para Vo < 3%
- [ ] Extrair data/hora do exame dos metadados
- [ ] Identificar labels adicionais (0xDE=Canal 5, 0xDA, 0xD9, etc.)

## Referências

- Elcat Vasoquant 1000: https://www.elcat.de/wp-content/uploads/a2101-9311_vq1000.d-ppg_prospekt_de.pdf
- Conversor WS1C: https://www.tgycyber.com/pt-BR/docs/ws1c
- Amato ACM. Propedêutica vascular. São Paulo: Amato - Instituto de Medicina Avançada; 2024.
  Capítulo 8, Propedêutica arterial armada; p. 106-167.

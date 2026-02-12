# D-PPG Vasoquant 1000 Reader

Aplicativo para leitura de dados do aparelho de fotopletismografia digital (D-PPG) Elcat Vasoquant 1000.

## Visão Geral

O Elcat Vasoquant 1000 é um aparelho de fotopletismografia usado para diagnóstico vascular. O software original só funciona em Windows antigo. Este projeto cria uma alternativa em Python para Mac/Linux/Windows.

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
- Exemplo: `A7 09` = 0x09A7 = 2471

### Caracteres de Controle Reconhecidos
- **0x10 (DLE)**: Data Link Escape - polling de status (vem sozinho, ~1x/segundo)
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
Erros médios vs laudo oficial: To ~1%, Ti 0%, Vo 0%, Th ~4%, Fo ~4%.

### Fluxo do Protocolo (Modo Impressora)
1. Vasoquant envia DLE (0x10) periodicamente para verificar impressora
2. App responde com ACK (0x06) → aparelho mostra "printer online"
   - Vasoview original envia ACK+ESC+I (3 bytes) e recebe 13 bytes de ID
3. Usuário exporta exame no Vasoquant
4. Vasoquant envia: ESC + Label + EOT + SOH + GS + tamanho + dados + metadados
5. App deve responder ACK após receber dados (pacote terminando em 00 04)
6. Vasoquant volta a enviar DLE para polling

## Uso do Aplicativo

### Executar
```bash
cd /path/to/dppg
python3 dppg_reader.py
```

### Passos para Capturar Dados
1. Clique em "Conectar TCP"
2. Aguarde "printer online" aparecer no Vasoquant
3. No Vasoquant, selecione um exame e exporte/imprima
4. Dados são capturados automaticamente
5. Clique em "Salvar CSV" para exportar

### Configurações Padrão
- **IP**: 192.168.0.234
- **Porta**: 1100
- **Auto-ACK**: Ativado (responde automaticamente ao polling)
- **Polling**: Passivo por padrão (baseado na análise do Vasoview original)
- **Socket Timeout**: 3 segundos (baseado na análise do Vasoview: usa timeouts longos)
- **TCP Keep-Alive**: Habilitado automaticamente (5s no macOS)

### Modos de Polling
| Modo | Comando | Descrição |
|------|---------|-----------|
| **Passivo** | - | Apenas responde ACK ao polling DLE do dispositivo (recomendado) |
| **ENQ** | 0x05 | Keep-alive binário ativo (usado quando autenticado) |
| **TST:CHECK** | ASCII | **SOMENTE VL320** - NÃO funciona com VQ1000! |
| **Desativado** | - | Não responde automaticamente (para debug) |

### Análise do Vasoview Original

#### Via API Monitor (captura Windows)
- **Timeouts infinitos**: Vasoview usa `MAXDWORD` (0xFFFFFFFF) para timeouts de leitura
- **Modo passivo**: Não faz polling ativo - apenas espera dados e responde
- **Porta**: COM2 (mapeada via `GetCommHandle`)

#### Via Disassembly de vl320hw.dll (análise profunda)
- **Aplicação PE32** (Qt4): ELCmain 2.exe é um launcher Qt fino, NÃO é 16-bit DOS
- **Arquitetura**: ELCmain → eCommon.dll → vl320hw.dll → porta serial
- **Serial thread** (0x100127c0): Loop principal de comunicação em background
- **Máquina de estados** (0x100118c0): Estados 1-10+, processa byte a byte
- **DLE handshake**: Responde ACK+ESC+I (3 bytes), recebe 13 bytes de ID
- **8N2**: Configuração serial confirmada com 2 stop bits (não 8N1)
- **Keep-alive**: SYN (0x16) ou ENQ (0x05), timeout 4 segundos
- **Dois protocolos distintos**: VQ1000 = binário ESC, VL320 = ASCII (TST:CHECK)

Esta análise confirma o modo "Passivo" como padrão e corrige erros da documentação anterior.

## Estrutura do Projeto

```
dppg/
├── CLAUDE.md              # Esta documentação
├── PROTOCOL.md            # Documentação detalhada do protocolo
├── dppg_reader.py         # Aplicativo principal com GUI
├── DPPG Reader.command    # Script para iniciar o app (duplo clique)
├── calibrate.py           # Script de calibração de parâmetros
├── compare_results.py     # Comparação com laudos oficiais
├── analyze_exam.py        # Análise detalhada de exames
├── laudos/                # Laudos oficiais para validação
│   ├── patient_A.pdf
│   ├── patient_B.pdf
│   ├── patient_C.pdf
│   └── teste1.pdf
├── app_original/          # Software original Vasoview para engenharia reversa
│   └── redist/
│       ├── dppg 2.dll     # DLL com algoritmos de cálculo (analisada)
│       └── ELCmain 2.exe  # Executável principal
└── ppg_data_*.csv/json    # Arquivos de dados exportados
```

## Parâmetros Quantitativos

O aplicativo calcula automaticamente os parâmetros diagnósticos da curva D-PPG:

| Parâmetro | Descrição | Unidade |
|-----------|-----------|---------|
| **To** | Venous refilling time - Tempo de reenchimento venoso | segundos |
| **Th** | Venous half amplitude time - Tempo de meia amplitude | segundos |
| **Ti** | Initial inflow time - Tempo de influxo inicial (extrapolação linear adaptativa) | segundos |
| **Vo** | Venous pump power - Potência da bomba venosa | % |
| **Fo** | Venous pump capacity - Capacidade da bomba venosa (integral da curva) | %·s |

### Taxa de Amostragem
- **4 Hz** (confirmado via análise de exercício: 64 amostras em 16 segundos)
- O hardware interno opera a 32.5 Hz, mas os dados exportados são decimados

### Conversão ADC → %PPG
- Fator de conversão: ~27 unidades ADC = 1% PPG
- Baseline: pré-calculado pelo hardware e armazenado junto com os dados (não calculado pela DLL)

### Gráfico Diagnóstico (Vo% × To)
O aplicativo gera um gráfico de dispersão Vo% vs To com zonas de referência:
- **Zona vermelha (esquerda)**: abnormal - To < 25s indica insuficiência venosa
- **Zona verde (direita)**: normal - To > 25s indica função venosa adequada

### Labels dos Canais
| Label | Byte | Descrição |
|-------|------|-----------|
| Lâ | 0xE2 | MID c/ Tq - Membro Inferior Direito, com Tourniquet |
| Lá | 0xE1 | MID s/ Tq - Membro Inferior Direito, sem Tourniquet |
| Là | 0xE0 | MIE c/ Tq - Membro Inferior Esquerdo, com Tourniquet |
| Lß | 0xDF | MIE s/ Tq - Membro Inferior Esquerdo, sem Tourniquet |

## Formato do CSV Exportado

```csv
block,exam_number,label,sample_index,value
0,1250,Lâ,0,2471
0,1250,Lâ,1,2472
...
```

## Formato do JSON Exportado

```json
{
  "export_timestamp": "2026-01-14T15:44:09",
  "sampling_rate_hz": 4.0,
  "blocks": [
    {
      "label": "Lâ",
      "label_desc": "MID c/ Tq",
      "exam_number": 1250,
      "samples": [...],
      "parameters": {
        "To_s": 28.0,
        "Th_s": 5.8,
        "Ti_s": 24.1,
        "Vo_percent": 5.9,
        "Fo_percent_s": 62
      }
    }
  ]
}
```

## Validação das Fórmulas (Engenharia Reversa da DLL)

Análise completa da biblioteca `dppg 2.dll` do software original Vasoview via disassembly
com radare2. A função principal de cálculo foi identificada em `fcn.100182c0` (1150 bytes).
Pseudocode completo em `app_original_v2/PSEUDOCODE_DPPG.md`.

### Descoberta Crítica: Cálculos usam aritmética INTEIRA

Todos os cálculos de parâmetros PPG usam **aritmética inteira** (sem FPU). As constantes
de ponto flutuante anteriormente documentadas (0.50, 0.125, 3.0, 100.0, etc.) são TODAS
usadas para **layout de impressão/renderização**, não para análise de sinal.

### Constantes REAIS do Cálculo (aritmética inteira)

| Valor | Endereço | Instrução | Uso Confirmado |
|-------|----------|-----------|----------------|
| `sar eax,1` (÷2) | 0x100183AF | shift | **Threshold Th = 50%** |
| `0x64` (100) | 0x100183EB | `imul` | Th: conversão amostras→centissegundos |
| `0x3E8` (1000) | 0x10018425 | `imul` | Vo: multiplicador para 0.1% |
| `0x0A` (10) | 0x1001848D | `cmp` | Ti: limiar adaptativo (10 unidades ADC) |
| `0x1E` (30) | 0x10018494 | `and`/`add` | Ti: janela rápida = 3 períodos × 10 |
| `0x3C` (60) | 0x10018497 | `and`/`add` | Ti: janela lenta = 6 períodos × 10 |
| `0x78` (120) | 0x10018510 | `cmp` | Ti: valor máximo (120 segundos) |
| `0x82` (130) | 0x100184D9 | `mov` | Ti: marcador de overflow |
| `0x3E8` (1000) | 0x100185E3 | `imul` | Fo: normalização permil |
| `sar eax,2` (÷4) | 0x100185F2 | shift | Fo: divisão pela taxa de amostragem |

### Constantes da DLL que são de IMPRESSÃO (NÃO são de cálculo PPG)

| Constante | Endereço (VA) | Uso Real |
|-----------|---------------|----------|
| `0.50` | 0x10035CD2 | String "printout" (NÃO é float) |
| `0.125` | 0x10039D68 | Layout de impressão: 1/8 espaçamento de coluna |
| `3.0` | 0x10039D40 | Layout: margem de página em cm |
| `2.0` | 0x10039DE0 | Layout: offset Y em cm |
| `100.0` | 0x10039D98 | Layout: 300.0/100.0 = 3.0cm largura coluna |
| `10.0` | 0x10039D58 | Layout: comparação de espaço restante na página |
| `12.0` | 0x10039D48 | Layout de impressão |
| `6.0` | 0x10039D50 | Layout de impressão |
| `72.0` | 0x10039D60 | Layout de impressão |
| `37.0` | 0x10039D80 | Layout: 0.37 fração de coluna |
| `70.0` | 0x10039D90 | Layout: 0.70 fração de largura da página |
| `300.0` | 0x10039DA0 | Layout: 3.0cm (300.0/100.0) |

### Fórmulas Confirmadas (Engenharia Reversa Completa)

```python
# Baseline: pré-calculado pelo hardware, armazenado junto com os dados
# NÃO é calculado pela DLL (vem no buffer de dados do exame)
baseline = valor_do_hardware

# Pico e endpoint: pré-calculados pelo hardware, ajustáveis pelo usuário
# O pico é ajustado: peak_index = peak_raw + 2*sr - 1
peak_index = valor_do_hardware_ajustado
end_index  = peak_index + offset_do_hardware  # ou INVALID se não detectado

# ===== To (Venous Refilling Time) =====
# Diferença simples entre endpoint e pico, em segundos
To = round((end_index - peak_index) / sampling_rate)  # inteiro, segundos
# Negativo se extrapolado (endpoint no último sample)

# ===== Th (Half-Amplitude Time) =====
# Busca linear do pico para frente: primeiro sample onde
# (sample - baseline) < (peak_value - baseline) / 2
half_amplitude = trunc_div(peak_value - baseline, 2)   # sar eax, 1
for i in range(peak, sample_count):
    if samples[i] - baseline < half_amplitude:
        Th_samples = i - peak
        break
Th = round(Th_samples * 10 / sampling_rate)  # décimos de segundo

# ===== Vo (Venous Pump Power) =====
# Porcentagem direta da amplitude em relação ao baseline
Vo = (peak_value - baseline) * 1000 / baseline  # décimos de %

# ===== Ti (Initial Inflow Time) — EXTRAPOLAÇÃO LINEAR ADAPTATIVA =====
# NÃO é cruzamento de threshold! Usa extrapolação linear da inclinação inicial.
#
# 1. Seleção adaptativa da janela temporal:
delta_3sec = peak_value - samples[peak + 3 * sr]   # queda em 3 segundos
if delta_3sec >= 10:    # limiar = 10 unidades ADC
    window = 3          # sinal de decaimento rápido: janela de 3s
else:
    window = 6          # sinal de decaimento lento: janela de 6s

# 2. Extrapolação linear:
target = peak + window * sr                         # índice alvo
drop = peak_value - samples[target]                 # queda na janela
if drop == 0:
    Ti = 130            # overflow (sinal plano)
else:
    Ti = round(window * (peak_value - baseline) / drop)  # segundos
    Ti = min(Ti, 120)   # clamped a 120s máximo; >120 → marcado 130

# Para decaimento exponencial típico, Ti/Th ≈ 2.0

# ===== Fo (Venous Pump Capacity) — INTEGRAL DA CURVA =====
# NÃO é simplesmente Vo × Th. É a integral (área sob a curva).
area = sum(samples[i] - baseline for i in range(peak, end))
# Correção trapezoidal:
rect_half = (samples[end-1] - baseline) * (end - peak) / 2
Fo = (area - rect_half) * 1000 / baseline / sampling_rate
# Negativo se extrapolado
```

### Resumo das Correções vs Documentação Anterior

| Item | Antes (ERRADO) | Agora (CORRETO) |
|------|----------------|-----------------|
| **Ti** | Cruzamento de threshold a 12.5% (0.125) | Extrapolação linear adaptativa (janela 3s ou 6s) |
| **Ti threshold** | Constante 0.125 da DLL | Não usa threshold; usa razão amplitude/queda |
| **Fo** | Vo × Th | Integral da curva (área sob a curva acima do baseline) |
| **Baseline** | Mediana dos primeiros 10 samples | Pré-calculado pelo hardware |
| **0.125** | Threshold de Ti | Espaçamento de coluna para impressão |
| **0.50** | Threshold de Th | String "printout" (não é float) |
| **3.0** | Threshold de To (3%) | Margem de página em cm |
| **Cálculos** | Aritmética de ponto flutuante (FPU) | Aritmética inteira pura |

## Precisão Atual dos Cálculos

Validado com 19 canais de exame de laudos oficiais VASOSCREEN (4 pacientes, 17 canais com sucesso).
Algoritmos de Ti (extrapolação linear adaptativa) e Fo (integral trapezoidal) implementados
conforme pseudocódigo reverso de `dppg 2.dll`.

### Resumo de Erros

| Parâmetro | Erro Médio | Erro Mediano | Status |
|-----------|------------|--------------|--------|
| **Vo** | **6.1%** | **1.0%** | ✅ Excelente - cálculo direto da amplitude |
| **To** | **20.6%** | **7.5%** | ✅ Bom para sinais normais |
| **Th** | **19.5%** | **8.0%** | ✅ Bom - 50% threshold crossing confirmado |
| **Ti** | **15.6%** | **11.8%** | ✅ Extrapolação linear adaptativa (melhorou de 42.1%) |
| **Fo** | **26.3%** | **10.1%** | ✅ Integral trapezoidal (melhorou de 51.9%) |
| **Global** | **18.8%** | **9.1%** | ✅ Mediana < 10% (melhorou de 28.9%) |

### Casos Normais (Vo > 3%) - Excelente precisão

| Exame | To erro | Th erro | Ti erro | Vo erro | Fo erro |
|-------|---------|---------|---------|---------|---------|
| 1250 (patient_A, MID c/Tq) | 2.4% | 8.0% | 0.0% | 3.0% | 7.3% |
| 1249 (patient_A, MID s/Tq) | 2.0% | 10.0% | 11.8% | 0.0% | 5.7% |
| 1248 (patient_A, MIE c/Tq) | 3.8% | 0.0% | 4.8% | 1.0% | 2.6% |

### Limitações Conhecidas

#### 1. Sinais de baixa amplitude (Vo < 3%)

Para sinais patológicos (insuficiência venosa severa), os erros são maiores:
- Relação sinal/ruído desfavorável
- Dificuldade na detecção automática do pico
- No software original, pico e endpoint são pré-calculados pelo hardware e
  ajustáveis manualmente pelo usuário

#### 2. Baseline

No software original, o baseline vem pré-calculado pelo hardware. Nossa implementação
calcula a mediana dos primeiros 10 samples, o que pode divergir do valor do hardware.

#### 3. Endpoint de recuperação (To)

No original, To = (end_marker - peak) / sr, com markers do hardware. Nós aproximamos
usando threshold crossing a 3% residual, o que pode divergir em sinais com recuperação lenta.

## Próximos Passos

### Prioridade média: Melhorar detecção de pico
1. **Melhorar detecção automática de pico para baixa amplitude (Vo < 3%)**

## TODO

- [x] Parsear corretamente o protocolo (separar header, dados, metadados)
- [x] Identificar e separar diferentes canais/medições
- [x] Extrair metadados (número do exame)
- [x] Melhorar visualização do gráfico PPG
- [x] Salvar em formato mais estruturado (JSON com metadados)
- [x] Documentar significado dos diferentes labels (Lâ, Lá, etc.)
- [x] Calcular parâmetros quantitativos (To, Th, Ti, Vo, Fo)
- [x] Gráfico diagnóstico Vo% × To(s)
- [x] Calibrar algoritmo com laudos originais (validado com 40 exames)
- [x] Confirmar taxa de amostragem (4 Hz)
- [x] ~~Documentar protocolo TST:CHECK alternativo~~ → TST:CHECK é exclusivo do VL320, não do VQ1000
- [x] ~~Implementar opção TST:CHECK no aplicativo~~ → Opção mantida mas marcada como VL320-only
- [x] Validar fórmulas via engenharia reversa da DLL (Vo, Th, To, Fo confirmados)
- [x] ~~Confirmar threshold Ti = 0.125 via DLL~~ → Ti NÃO usa threshold (usa extrapolação linear)
- [x] Melhorar estabilidade de conexão (TCP keep-alive + TST:CHECK padrão)
- [x] Analisar Vasoview original via API Monitor (modo passivo, timeouts infinitos)
- [x] Desassemblar bloco de código do Ti na DLL (fcn.100182c0 - extrapolação adaptativa)
- [x] Investigar constantes FPU da DLL (todas são de layout de impressão, não cálculo)
- [x] Implementar Ti como extrapolação linear adaptativa (substituir threshold crossing)
- [x] Implementar Fo como integral trapezoidal (substituir Vo×Th)
- [x] Re-validar contra exames após correções de Ti e Fo (mediana global 9.1%)
- [x] Decodificar metadados do protocolo (baseline, peak, To, Th, Ti, Fo, flags - 32/32 verificados)
- [x] Usar valores do hardware (metadados) quando disponíveis para cálculo de parâmetros
- [x] Engenharia reversa profunda de vl320hw.dll (protocolo binário ESC completo)
- [x] Corrigir configuração serial: 8N2 (2 stop bits), não 8N1
- [x] Identificar handshake completo: ACK+ESC+I (3 bytes), não apenas ACK
- [x] Separar protocolos VQ1000 (binário ESC) vs VL320 (ASCII TST:CHECK)
- [ ] Testar handshake estendido ACK+ESC+I com hardware real
- [ ] Implementar modo de comando binário ESC do VQ1000
- [ ] Melhorar detecção de pico para Vo < 3%
- [ ] Extrair data/hora do exame dos metadados
- [ ] Identificar labels adicionais (0xDE=Canal 5, 0xDA, 0xD9, etc.)

## Referências

- Elcat Vasoquant 1000: https://www.elcat.de/wp-content/uploads/a2101-9311_vq1000.d-ppg_prospekt_de.pdf
- Conversor WS1C: https://www.tgycyber.com/pt-BR/docs/ws1c

# D-PPG Vasoquant 1000 Reader

Aplicativo para leitura de dados do aparelho de fotopletismografia digital (D-PPG) Elcat Vasoquant 1000.

## Visão Geral

O Elcat Vasoquant 1000 é um aparelho de fotopletismografia usado para diagnóstico vascular. O software original só funciona em Windows antigo. Este projeto cria uma alternativa em Python para Mac/Linux/Windows.

## Hardware

### Aparelho
- **Modelo**: Elcat Vasoquant 1000 D-PPG
- **Interface original**: Porta serial RS-232
- **Baud rate**: 9600
- **Configuração**: 8N1 (8 data bits, No parity, 1 stop bit)
- **Controle de fluxo**: Nenhum

### Conversor Serial-WiFi
- **Modelo**: TGY Cyber WS1C
- **Documentação**: https://www.tgycyber.com/pt-BR/docs/ws1c
- **IP configurado**: 192.168.0.234
- **Porta TCP**: 1100 (padrão para Serial 1)

## Protocolo de Comunicação

O Vasoquant suporta dois modos de comunicação:

### Modo 1: Emulação de Impressora (DLE/ACK) - Padrão

Protocolo baseado em impressora serial (modo padrão):

1. Aparelho envia **DLE (0x10)** periodicamente para verificar se "impressora" está online
2. Devemos responder com **ACK (0x06)** para indicar que estamos prontos
3. Se não respondermos, aparelho mostra "printer offline"

### Modo 2: Comunicação Direta (TST:CHECK)

Protocolo ASCII alternativo para comunicação programática:

1. Host envia **TST:CHECK\r** a cada 1-2 segundos
2. Equipamento responde com **OK\r**
3. Se não receber TST:CHECK por ~5 segundos, entra em modo watchdog
4. Comandos disponíveis: ACQ:START, ACQ:STOP, S#A:ON/OFF, CFG:GET/SET

**Nota**: Ative a opção "TST:CHECK" na interface para usar este modo.

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

### Fluxo do Protocolo
1. Vasoquant envia DLE (0x10) periodicamente para verificar impressora
2. App responde com ACK (0x06) → aparelho mostra "printer online"
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
- **TST:CHECK**: Ativado por padrão (keep-alive a cada 1s para estabilidade)
- **TCP Keep-Alive**: Habilitado automaticamente (5s no macOS)

## Estrutura do Projeto

```
dppg/
├── CLAUDE.md           # Esta documentação
├── PROTOCOL.md         # Documentação detalhada do protocolo
├── dppg_reader.py      # Aplicativo principal com GUI
├── calibrate.py        # Script de calibração de parâmetros
└── ppg_data_*.csv/json # Arquivos de dados exportados
```

## Parâmetros Quantitativos

O aplicativo calcula automaticamente os parâmetros diagnósticos da curva D-PPG:

| Parâmetro | Descrição | Unidade |
|-----------|-----------|---------|
| **To** | Venous refilling time - Tempo de reenchimento venoso (início do exercício até retorno ao baseline) | segundos |
| **Th** | Venous half amplitude time - Tempo de meia amplitude (do pico até 50% da amplitude) | segundos |
| **Ti** | Initial inflow time - Tempo de influxo inicial (do pico até 90% de recuperação) | segundos |
| **Vo** | Venous pump power - Potência da bomba venosa (amplitude pico-baseline) | % |
| **Fo** | Venous pump capacity - Capacidade da bomba venosa (Fo = Vo × Th) | %·s |

### Taxa de Amostragem
- **4 Hz** (confirmado via análise de exercício: 64 amostras em 16 segundos)
- O hardware interno opera a 32.5 Hz, mas os dados exportados são decimados

### Conversão ADC → %PPG
- Fator de conversão: ~27 unidades ADC = 1% PPG
- Baseline: calculado dos primeiros 10 valores (antes do exercício)

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

## Precisão dos Cálculos

O algoritmo foi calibrado com 4 exames do laudo oficial VASOSCREEN. Erro médio geral: **~6.9%**

| Parâmetro | Erro Médio | Observação |
|-----------|------------|------------|
| **Vo** | ~2.5% | Excelente - cálculo direto da amplitude |
| **Ti** | ~5.2% | Bom - usa 88% de recuperação |
| **To** | ~5.8% | Bom - usa 97% de recuperação |
| **Th** | ~10.0% | Aceitável - usa 52% de recuperação |
| **Fo** | ~11.0% | Aceitável - derivado (Fo = Vo × Th) |

### Limitações Conhecidas

1. **Casos com torniquete**: O sinal pode não retornar ao baseline original. O algoritmo usa o maior entre baseline inicial e baseline estável como referência.

2. **Extrapolação**: Se o sinal não atinge o nível de cruzamento, valores são extrapolados linearmente.

## Validação das Fórmulas (Engenharia Reversa da DLL)

Análise da biblioteca `dppg_2.dll` do software original Vasoview:

| Parâmetro | Fórmula | Status | Evidências |
|-----------|---------|--------|------------|
| **Vo** | `(amplitude/baseline) × 100%` | ✅ Confirmado | Unidade `%`, constante `100.0` |
| **Th** | `50% de recuperação` | ✅ Confirmado | Constante `0.5` encontrada 11x |
| **Ti** | `90% de recuperação` | ⚠️ Provável | Inteiro `90` encontrado 4x |
| **To** | `97% de recuperação` | ⚠️ Provável | Inteiro `97` encontrado 7x |
| **Fo** | `Vo × Th` | ✅ Confirmado | Unidade `%s` = `% × s` |

### Fórmulas Detalhadas (Calibradas)

```
# Baselines
initial_baseline = mediana(amostras[0:10])
stable_baseline  = mediana(amostras[-20:])
reference_baseline = max(stable_baseline, initial_baseline)

# Amplitudes
amplitude_vo  = peak_value - initial_baseline
amplitude_ref = peak_value - reference_baseline

# Parâmetros (thresholds calibrados com laudos originais)
Vo = (amplitude_vo / initial_baseline) × 100%
Th = tempo até cruzar (initial_baseline + amplitude_vo × 0.48)   # 52% recuperação
Ti = tempo até cruzar (reference_baseline + amplitude_ref × 0.12) # 88% recuperação
To = tempo até cruzar (reference_baseline + amplitude_ref × 0.03) # 97% recuperação
Fo = Vo × Th
```

### Constantes Encontradas na DLL

| Constante | Ocorrências | Uso |
|-----------|-------------|-----|
| `0.5` | 11x | Threshold Th (50%) |
| `100.0` | 1x | Conversão para % |
| `10`, `20` | janelas | Baseline detection |
| `90`, `97` | thresholds | Ti e To (provável) |

## TODO

- [x] Parsear corretamente o protocolo (separar header, dados, metadados)
- [x] Identificar e separar diferentes canais/medições
- [x] Extrair metadados (número do exame)
- [x] Melhorar visualização do gráfico PPG
- [x] Salvar em formato mais estruturado (JSON com metadados)
- [x] Documentar significado dos diferentes labels (Lâ, Lá, etc.)
- [x] Calcular parâmetros quantitativos (To, Th, Ti, Vo, Fo)
- [x] Gráfico diagnóstico Vo% × To(s)
- [x] Calibrar algoritmo com laudos originais (erro médio ~6.9%)
- [x] Confirmar taxa de amostragem (4 Hz)
- [x] Documentar protocolo TST:CHECK alternativo
- [x] Implementar opção TST:CHECK no aplicativo
- [x] Validar fórmulas via engenharia reversa da DLL (Vo, Th, Fo confirmados)
- [x] Melhorar estabilidade de conexão (TCP keep-alive + TST:CHECK padrão)
- [ ] Extrair data/hora do exame dos metadados
- [ ] Identificar labels adicionais (0xDE=Canal 5, 0xDA, 0xD9, etc.)

## Referências

- Elcat Vasoquant 1000: https://www.elcat.de/wp-content/uploads/a2101-9311_vq1000.d-ppg_prospekt_de.pdf
- Conversor WS1C: https://www.tgycyber.com/pt-BR/docs/ws1c

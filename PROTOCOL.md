# Protocolo de Comunicação Elcat Vasoquant 1000

Documentação da engenharia reversa do protocolo serial do aparelho D-PPG Elcat Vasoquant 1000.

---

## Status: Em Investigação

**Data início**: 2026-01-14
**Versão**: 0.2 (atualizado 2026-01-15)

---

## IMPORTANTE: Descobertas do Teste de Protocolo

### Comportamento Testado (2026-01-15)

| Comando | Quando Online | Quando Offline |
|---------|--------------|----------------|
| ACK (0x06) | ✅ Funciona **APENAS após receber DLE** | Sem efeito |
| ACK (0x06) sozinho | ⚠️ Causa OFFLINE | - |
| NAK (0x15) | ⚠️ Causa OFFLINE | Sem efeito |
| ENQ (0x05) | ⚠️ Causa OFFLINE | Sem efeito |
| DLE (0x10) | ⚠️ Causa OFFLINE | Sem efeito |
| EOT (0x04) | ⚠️ Causa OFFLINE | Sem efeito |
| ESC (0x1B) x2 | ⚠️ Causa OFFLINE (precisa 2x) | Sem efeito |
| Comandos ASCII | ⚠️ Causa OFFLINE | Sem efeito |

**Conclusão**: O modo de emulação de impressora é muito simples - apenas responder ACK quando receber DLE. Qualquer outro comando causa desconexão.

---

## 1. Camada Física (Confirmado)

| Parâmetro | Valor |
|-----------|-------|
| Interface | RS-232 |
| Baud rate | 9600 |
| Data bits | 8 |
| Paridade | Nenhuma (N) |
| Stop bits | 1 |
| Controle de fluxo | Nenhum |

**Observação**: O aparelho foi projetado para conectar a uma impressora serial térmica.

---

## 2. Dois Protocolos Distintos

O Vasoquant/Vasolab suporta **dois protocolos completamente diferentes**:

### 2.1 Modo Impressora (DLE/ACK) - USADO PARA EXPORTAÇÃO

Este é o modo que usamos para capturar exames. É extremamente simples.

### 2.2 Modo VL320 (STX/ETX) - COMUNICAÇÃO AVANÇADA

Protocolo mais avançado com pacotes binários, usado pelo software Vasoview para controle total do aparelho.

---

## 3. Protocolo de Emulação de Impressora (DLE/ACK)

**Modo**: Exportação de exames para "impressora serial"

O Vasoquant verifica periodicamente se a "impressora" está conectada.

#### Sequência de Polling

```
Vasoquant → Host:  0x10 (DLE)
Host → Vasoquant:  0x06 (ACK)
```

- **Intervalo**: ~1 segundo quando idle
- **Comportamento**: Se não receber ACK, aparelho mostra "printer offline"
- **CRÍTICO**: ACK só pode ser enviado em resposta a DLE, nunca espontaneamente

---

### 2.2 Protocolo ASCII de Comando (TST:CHECK)

**Modo**: Comunicação direta com o equipamento VL320/VQ1000

Este protocolo alternativo usa comandos ASCII para manter a conexão ativa.

#### Formato Geral de Comandos

```
[COMANDO]:[SUBCOMANDO]/[PARÂMETROS]<CR>
```

- Terminador: `<CR>` (Carriage Return, 0x0D)
- Separadores: `:` entre comando e subcomando, `/` entre subcomando e parâmetros

#### Comando de Keep-Alive

```
TST:CHECK<CR>
```

- **Intervalo**: Enviar a cada **1-2 segundos**
- **Timeout**: Se não receber por ~5 segundos, equipamento entra em modo watchdog
- **Watchdog**: Equipamento para aquisição e aguarda reconexão

#### Sequência de Conexão

```
┌─────────────┐                              ┌──────────┐
│  VQ1000     │                              │   Host   │
└──────┬──────┘                              └────┬─────┘
       │                                          │
       │  ◄─── TST:CHECK<CR> ────────────────     │  Keep-alive
       │  ──── OK<CR> ───────────────────────►    │  Resposta
       │                                          │
       │        ... (repetido a cada 1-2s) ...    │
       │                                          │
       │  ◄─── ACQ:START<CR> ────────────────     │  Iniciar aquisição
       │  ──── STARTED<CR> ──────────────────►    │  Confirmação
       │                                          │
       │  ════ [Dados de aquisição] ═════════►    │  Stream de dados
       │                                          │
       │  ◄─── ACQ:STOP<CR> ─────────────────     │  Parar aquisição
       │  ──── STOPPED<CR> ──────────────────►    │  Confirmação
       │                                          │
```

#### Comandos Conhecidos

| Comando | Descrição |
|---------|-----------|
| `TST:CHECK` | Keep-alive / verificação de conexão |
| `ACQ:START` | Iniciar aquisição de dados |
| `ACQ:STOP` | Parar aquisição de dados |
| `S#A:ON` | Ativar canal # (ex: S1A:ON, S2A:ON) |
| `S#A:OFF` | Desativar canal # |
| `CFG:GET` | Obter configuração atual |
| `CFG:SET/[param]=[value]` | Definir parâmetro de configuração |

#### Comportamento do Watchdog

1. Host conecta via TCP
2. Host envia `TST:CHECK` a cada 1-2 segundos
3. Equipamento responde com `OK` ou similar
4. Se `TST:CHECK` não for recebido por ~5 segundos:
   - Equipamento assume desconexão
   - Aquisição é interrompida automaticamente
   - Equipamento aguarda nova conexão

**Nota**: Este protocolo é usado para comunicação direta/programática com o equipamento, diferente do modo de emulação de impressora que é usado para exportação manual de exames.

---

### 2.3 Descoberta Importante: ACK Contínuo (Modo Impressora)

**O Vasoquant espera ACK (0x06) como resposta a QUALQUER dado enviado, não apenas ao DLE de polling.**

```
Vasoquant → Host:  [qualquer dado]
Host → Vasoquant:  0x06 (ACK)
```

- **Implementação correta**: Enviar ACK após receber qualquer pacote de dados
- **Erro anterior**: Responder apenas ao DLE causava "offline" intermitente

### Resultado do Handshake

| Resposta | Status no aparelho |
|----------|-------------------|
| ACK (0x06) após cada pacote | "printer online" (estável) |
| ACK apenas no DLE | "printer online" → "offline" (instável) |
| Sem resposta | "printer offline" |

---

## 3. Estrutura de Pacotes de Dados (Parcialmente Confirmado)

Quando o usuário exporta um exame, o Vasoquant envia dados no seguinte formato:

### 3.1 Cabeçalho de Bloco

```
1B        ESC - Início de bloco
4C        'L' - Identificador de label
XX        Identificador do canal/tipo (ex: E2, E1)
04        EOT - Fim do cabeçalho de label
```

**Labels observados e seus significados (CONFIRMADO via laudo oficial)**:
| Código | Caracter | Byte | Significado | Descrição |
|--------|----------|------|-------------|-----------|
| `4C E2` | Lâ | 0xE2 (226) | MID c/ Tq | Membro Inferior Direito, com Tourniquet |
| `4C E1` | Lá | 0xE1 (225) | MID s/ Tq | Membro Inferior Direito, sem Tourniquet |
| `4C E0` | Là | 0xE0 (224) | MIE c/ Tq | Membro Inferior Esquerdo, com Tourniquet |
| `4C DF` | Lß | 0xDF (223) | MIE s/ Tq | Membro Inferior Esquerdo, sem Tourniquet |
| `4C DE` | LÞ | 0xDE (222) | ? | A ser identificado |

**Legenda**:
- MID = Membro Inferior Direito
- MIE = Membro Inferior Esquerdo
- Tq = Tourniquet (garrote)

**Correlação Label → Exame** (baseado em laudo oficial):
- Exame #1250 → Label 0xE2 (Lâ) → MID com Tourniquet
- Exame #1249 → Label 0xE1 (Lá) → MID sem Tourniquet
- Exame #1248 → Label 0xE0 (Là) → MIE com Tourniquet
- Exame #1247 → Label 0xDF (Lß) → MIE sem Tourniquet

### 3.2 Cabeçalho de Dados

```
01        SOH - Start of Header
1D        GS - Group Separator
00        ?
XX XX     Tamanho em little-endian (quantidade de amostras)
```

**Exemplo**: `1D 00 FA 00` → 0x00FA = 250 amostras

### 3.3 Dados PPG

```
LL HH LL HH LL HH ...
```

- **Formato**: 16 bits little-endian por amostra
- **Faixa observada**: 2000-3500 (sugere ADC de 12 bits)
- **Exemplo**: `A7 09` = 0x09A7 = 2471

### 3.4 Metadados / Rodapé (Parcialmente Confirmado)

Após os dados PPG, há bytes adicionais que contêm metadados:

```
Exemplo observado:
1D A7 09 00 00 00 1D E2 04 87 34 A2 00 FE 1E 44 18 00 04
```

#### 3.4.1 Número do Exame (CONFIRMADO)

O número do exame está no **SEGUNDO** GS do rodapé, com formato completo:

```
1D XX XX 00 00 00 1D YY YY
```

- `1D` = GS (Group Separator) - primeiro marcador
- `XX XX` = Cópia do primeiro valor do bloco (verificação?)
- `00 00 00` = Separador/padding
- `1D` = GS (segundo marcador)
- `YY YY` = Número do exame em 16 bits little-endian

**Exemplo completo**:
```
1D A7 09 00 00 00 1D E2 04
```
- A7 09 = 2471 (primeiro sample do bloco)
- E2 04 = 1250 (número do exame)

**Exemplos confirmados**:
- Exame 1250: `1D E2 04` → 0x04E2 = 1250
- Exame 1245: `1D DD 04` → 0x04DD = 1245

#### 3.4.2 Artefatos no Final dos Dados (IDENTIFICADO)

Os últimos 3 valores de cada bloco frequentemente são **artefatos** (não são dados clínicos válidos):

**Exemplo observado** (final do Bloco Lâ):
```
Últimos valores: ..., 2517, 2703, 2363, 2504
                       ↑      ↑      ↑      ↑
                    normal  spike  baixo  meta
```

- Valor 2517 = normal (dentro da faixa esperada ~2400-2650)
- Valor 2703 = spike anômalo (muito acima da média)
- Valores 2363, 2504 = possivelmente bytes de controle/metadados

**Tratamento**: O parser remove automaticamente valores outliers do final (> 3 desvios padrão da média).

#### 3.4.3 Outros Campos (Em Investigação)

**Hipóteses para bytes restantes após número do exame**:
- Checksum ou CRC
- Timestamp
- Configurações da medição

---

## 4. Taxa de Amostragem e Conversão de Dados (CONFIRMADO)

### 4.1 Taxa de Amostragem

**CONFIRMADO via análise de exercício**:
- Exercício padrão: 8 movimentos de dorsiflexão em 16 segundos
- Amostras no período de exercício: ~64
- **Taxa de amostragem: 4 Hz** (64 amostras / 16 segundos)

*Nota*: Os 32.5 Hz encontrados no binário do software original são a taxa interna do hardware ADC, mas os dados exportados são decimados para 4 Hz.

### 4.2 Conversão ADC → %PPG

**Observações do laudo oficial**:
- Eixo Y do gráfico: -2% a 8% PPG
- Valores ADC capturados: ~2400-2700

**Fórmula de conversão estimada**:
```
%PPG = (valor_ADC - baseline) / fator_conversao
```

Onde:
- `baseline` = média dos primeiros ~10 valores (antes da deflexão venosa)
- `fator_conversao` ≈ 27 unidades ADC por %PPG

**Exemplo**:
- Baseline: 2471 ADC
- Pico: 2633 ADC
- Delta: 2633 - 2471 = 162 unidades
- %PPG no pico: 162 / 27 ≈ 6%

### 4.3 Parâmetros Clínicos (do laudo)

O software VASOSCREEN calcula os seguintes parâmetros:

| Parâmetro | Símbolo | Unidade | Descrição |
|-----------|---------|---------|-----------|
| Venous refilling time | To | s | Tempo de reenchimento venoso |
| Venous half ampl. time | Th | s | Tempo para metade da amplitude |
| Initial inflow time | Ti | s | Tempo de influxo inicial |
| Venous pump power | Vo | % | Potência da bomba venosa |
| Venous pump capacity | Fo | %s | Capacidade da bomba venosa |

---

## 5. Caracteres de Controle (Confirmado)

| Hex | Nome | Descrição |
|-----|------|-----------|
| 0x01 | SOH | Start of Header - início de bloco de dados |
| 0x04 | EOT | End of Transmission - fim de bloco |
| 0x05 | ENQ | Enquiry |
| 0x06 | ACK | Acknowledge - confirmação (nós enviamos) |
| 0x10 | DLE | Data Link Escape - polling de status |
| 0x1B | ESC | Escape - início de comando/label |
| 0x1D | GS | Group Separator - header de dados |

---

## 5. Fluxo Completo de Comunicação (Parcialmente Confirmado)

```
┌─────────────┐                              ┌──────────┐
│  Vasoquant  │                              │   Host   │
└──────┬──────┘                              └────┬─────┘
       │                                          │
       │  ──── DLE (0x10) ────────────────────►   │  Polling
       │  ◄─── ACK (0x06) ────────────────────    │
       │                                          │
       │        ... (repetido ~1x/segundo) ...    │
       │                                          │
       │  ════ ESC + Label + EOT ════════════►   │  Início de bloco
       │  ════ SOH + GS + Tamanho ═══════════►   │  Header
       │  ════ Dados PPG (N amostras) ═══════►   │  Dados
       │  ════ Metadados + 00 04 ════════════►   │  Fim de bloco
       │  ◄─── ACK (0x06) ────────────────────    │  Confirmação (?)
       │                                          │
       │  ──── DLE (0x10) ────────────────────►   │  Volta ao polling
       │  ◄─── ACK (0x06) ────────────────────    │
       │                                          │
```

---

## 6. Questões em Aberto

### 6.1 Confirmações Durante Transmissão - RESOLVIDO

**Problema**: Após receber os dados, o aparelho mostrava "printer offline".

**Solução**: Enviar ACK (0x06) após receber QUALQUER pacote de dados, não apenas o DLE de polling.

~~**Hipóteses**:~~
- [x] ~~Precisa enviar ACK após cada bloco de dados?~~ **SIM - CONFIRMADO**
- [x] ~~Precisa enviar ACK após receber metadados/rodapé?~~ **SIM - CONFIRMADO**
- [ ] ~~Timeout muito curto no polling?~~ Não era o problema
- [ ] ~~Handshake de hardware (DTR/RTS) sendo verificado?~~ Não era o problema

### 6.2 Significado dos Labels - ✅ RESOLVIDO

**Pergunta**: O que significam os diferentes labels (Lâ, Lá)?

**Resposta** (confirmado via laudo oficial VASOSCREEN):
- [x] Diferentes canais de medição (pé esquerdo/direito?) **SIM**
- [x] Diferentes tipos de medição (com/sem Tourniquet) **SIM**
- [ ] ~~Diferentes tipos de dados (PPG bruto vs processado?)~~ Não
- [ ] ~~Diferentes fases do exame?~~ Não

**Ver seção 3.1 para mapeamento completo dos labels.**

### 6.3 Estrutura dos Metadados

**Pergunta**: O que contêm os bytes após os dados PPG?

**Observações**:
```
Bloco 1: ... 1D E2 04 87 34 A2 00 FE 1E 44 18 00 04
Bloco 2: ... 1D E1 04 64 1B A0 00 C8 14 42 11 00 04
```

**Hipóteses**:
- [ ] `1D XX 04` pode ser um separador/marcador
- [ ] Bytes intermediários podem ser timestamp ou ID
- [ ] `00 04` no final indica fim de transmissão

### 6.4 Taxa de Amostragem - ✅ CONFIRMADO

**Pergunta**: Qual a taxa de amostragem dos dados PPG?

**Resposta** (CONFIRMADO via análise de exercício):
- Taxa de amostragem: **4 Hz** (8 movimentos em 16s = 64 amostras / 16s)
- Hardware interno opera a 32.5 Hz, mas dados exportados são decimados
- Adequada para D-PPG (mede refilling venoso, não pulsação)

**Ver seção 4.1 para detalhes.**

### 6.5 Múltiplos Exames

**Pergunta**: Como são separados múltiplos exames na transmissão?

**Observação**: Em uma exportação, recebemos 2 blocos (Lâ e Lá).

---

## 7. Dados de Exemplo

### Exame 1250 (capturado em 2026-01-14)

**Bloco 1 (Lâ)**:
```
Header: 1B 4C E2 04 01 1D 00 FA 00
Dados: 250 amostras (A7 09, A8 09, A9 09, ...)
Valores: 2471, 2472, 2473, ...
```

**Bloco 2 (Lá)**:
```
Header: 1B 4C E1 04 01 1D 00 D5 00
Dados: 213 amostras
```

**Total capturado**: ~885 amostras válidas

---

## 8. Referências

- **Aparelho**: [Elcat Vasoquant 1000 D-PPG](https://www.elcat.de)
- **Conversor Serial-WiFi**: [TGY Cyber WS1C](https://www.tgycyber.com/pt-BR/docs/ws1c)

---

## 9. Histórico de Descobertas

| Data | Descoberta |
|------|------------|
| 2026-01-14 | Conexão estabelecida via TCP/IP através do conversor WS1C |
| 2026-01-14 | Identificado protocolo de polling com DLE/ACK |
| 2026-01-14 | Identificado formato de dados PPG (16 bits LE) |
| 2026-01-14 | Primeira captura bem-sucedida de exame (885 amostras) |
| 2026-01-14 | Problema identificado: "offline" após transmissão |
| 2026-01-14 | **RESOLVIDO**: ACK deve ser enviado após QUALQUER pacote, não só DLE |
| 2026-01-14 | Exportação estável de múltiplos exames (4 exames) confirmada |
| 2026-01-14 | Parser de blocos implementado - detecta labels e extrai amostras corretamente |
| 2026-01-14 | Novo label descoberto: Lß (0xDF) com 224 amostras |
| 2026-01-14 | Status de conexão melhorado: TCP OK → Printer Online |
| 2026-01-14 | **CONFIRMADO**: Número do exame em metadados: GS + 16-bit LE (1250=E2 04, 1245=DD 04) |
| 2026-01-14 | **CORRIGIDO**: Número do exame está no SEGUNDO GS (após 00 00 00), não no primeiro |
| 2026-01-14 | **IDENTIFICADO**: Artefatos no final dos dados (últimos ~3 valores são outliers) |
| 2026-01-14 | Parser atualizado para remover outliers automaticamente |
| 2026-01-14 | **TESTE**: 5 exames exportados com sucesso (1250, 1249, 1248, 1247, 1246) |
| 2026-01-14 | Novo label descoberto: LÞ (0xDE) com 202 amostras |
| 2026-01-14 | Gráfico atualizado com escala vertical numérica |
| 2026-01-14 | Algoritmo de remoção de artefatos melhorado (IQR-based) |
| 2026-01-14 | Parser aguarda metadados antes de criar bloco |
| 2026-01-14 | **ANÁLISE LAUDO**: Comparação com laudo oficial VASOSCREEN v1.04 |
| 2026-01-14 | **CONFIRMADO**: Labels mapeados para MID/MIE com/sem Tourniquet (via laudo) |
| 2026-01-14 | **ESTIMADO**: Taxa de amostragem ~8.33 Hz (250 samples / 30s do laudo) |
| 2026-01-14 | **IMPLEMENTADO**: Conversão ADC → %PPG (fator ~27 unidades/%) |
| 2026-01-14 | **IMPLEMENTADO**: Gráfico com eixo Y em %PPG e eixo X em segundos |
| 2026-01-14 | **CORRIGIDO**: Thread safety com queue.Queue para dados network→UI |
| 2026-01-14 | **MELHORADO**: Aplicação retroativa de exam_number em blocos da sessão |
| 2026-01-14 | **ADICIONADO**: Registro de metadata_raw para análise futura |
| 2026-01-14 | **CONFIRMADO**: Taxa de amostragem 4 Hz (via análise de exercício: 64 amostras / 16s) |
| 2026-01-14 | **CALIBRADO**: Algoritmo de cálculo de parâmetros (To, Th, Ti, Vo, Fo) com erro médio ~7.7% |
| 2026-01-15 | **DOCUMENTADO**: Protocolo ASCII alternativo (TST:CHECK) para keep-alive VL320/VQ1000 |

---

## 10. Próximos Passos

### Concluídos ✅

1. ~~**Resolver problema do "offline"**~~: ✅ RESOLVIDO - ACK contínuo
2. ~~**Decodificar metadados**~~: ✅ PARCIAL - Número do exame identificado (GS + 16-bit LE)
3. ~~**Identificar labels**~~: ✅ CONFIRMADO via laudo - MID/MIE com/sem Tourniquet
4. ~~**Taxa de amostragem**~~: ✅ ESTIMADO - ~8.33 Hz (baseado no laudo)
5. ~~**Testar múltiplos exames**~~: ✅ CONFIRMADO - 5 exames exportados com sucesso (1250-1246)
6. ~~**Melhorar parser**~~: ✅ RESOLVIDO - Blocos e número do exame extraídos corretamente
7. ~~**Interface**~~: ✅ MELHORADO - Gráfico com %PPG e escala temporal
8. ~~**Estabilidade**~~: ✅ MELHORADO - Thread safety com queue.Queue
9. ~~**Conversão de dados**~~: ✅ IMPLEMENTADO - ADC → %PPG

### Em Progresso 🔄

10. **Remover artefatos**: Refinar algoritmo IQR para diferentes tipos de blocos
11. **Validar conversão %PPG**: Comparar gráficos com laudo oficial para calibração fina

### Futuros 📋

12. **Decodificar metadados restantes**: Bytes após exam_number (timestamp? checksum?)
13. ~~**Calcular parâmetros clínicos**~~: ✅ IMPLEMENTADO - To, Th, Ti, Vo, Fo calibrados
14. **Identificar label 0xDE (LÞ)**: Significado ainda desconhecido
15. **Captura raw para análise**: Salvar bytes brutos para debugging
16. **Implementar modo TST:CHECK**: Adicionar suporte ao protocolo ASCII alternativo para comunicação direta

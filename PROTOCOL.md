# Protocolo de Comunicação Elcat Vasoquant 1000

Documentação da engenharia reversa do protocolo serial do aparelho D-PPG Elcat Vasoquant 1000.

---

## Status: Em Investigação

**Data início**: 2026-01-14
**Versão**: 0.1

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

## 2. Handshake / Polling (Confirmado)

O Vasoquant verifica periodicamente se a "impressora" está conectada.

### Sequência de Polling

```
Vasoquant → Host:  0x10 (DLE)
Host → Vasoquant:  0x06 (ACK)
```

- **Intervalo**: ~1 segundo quando idle
- **Comportamento**: Se não receber ACK, aparelho mostra "printer offline"

### Descoberta Importante: ACK Contínuo

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

**Labels observados**:
- `4C E2` = "Lâ" (canal/medição tipo â)
- `4C E1` = "Lá" (canal/medição tipo á)

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

### 3.4 Metadados / Rodapé (Em Investigação)

Após os dados PPG, há bytes adicionais que parecem conter metadados:

```
Exemplo observado:
1D A7 09 00 00 00 1D E2 04 87 34 A2 00 FE 1E 44 18 00 04
```

**Hipóteses**:
- Checksum ou CRC
- Timestamp
- Número do exame
- Configurações da medição

---

## 4. Caracteres de Controle (Confirmado)

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

### 6.2 Significado dos Labels

**Pergunta**: O que significam os diferentes labels (Lâ, Lá)?

**Hipóteses**:
- [ ] Diferentes canais de medição (pé esquerdo/direito?)
- [ ] Diferentes tipos de dados (PPG bruto vs processado?)
- [ ] Diferentes fases do exame?

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

### 6.4 Taxa de Amostragem

**Pergunta**: Qual a taxa de amostragem dos dados PPG?

**Informação necessária**:
- Manual técnico do equipamento
- Ou análise temporal dos dados (se tiver timestamp)

**Hipóteses comuns para PPG**:
- [ ] 50 Hz
- [ ] 100 Hz
- [ ] 200 Hz

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

---

## 10. Próximos Passos

1. ~~**Resolver problema do "offline"**~~: ✅ RESOLVIDO - ACK contínuo
2. **Decodificar metadados**: Entender estrutura do rodapé
3. **Identificar labels**: Descobrir significado de Lâ vs Lá
4. **Taxa de amostragem**: Determinar frequência dos dados PPG
5. ~~**Testar múltiplos exames**~~: ✅ CONFIRMADO - 4 exames exportados com sucesso
6. **Melhorar parser**: Separar blocos de dados corretamente
7. **Interface**: Mostrar dados de forma mais organizada

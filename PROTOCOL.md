# Protocolo de Comunicação Elcat Vasoquant 1000

Documentação completa do protocolo serial do aparelho D-PPG Elcat Vasoquant 1000,
obtida por engenharia reversa (captura de dados, análise de DLLs, disassembly de vl320hw.dll).

**Versão**: 2.0 (2026-02-11)

---

## 1. Camada Física

| Parâmetro | Valor |
|-----------|-------|
| Interface | RS-232 |
| Baud rate | **9600** (configurável: 4800 ou 9600, via INI `Hardware/VQ1000bps`) |
| Data bits | 8 |
| Paridade | Nenhuma (N) |
| Stop bits | **2** (TWOSTOPBITS) |
| Controle de fluxo | Nenhum |
| Buffers (driver) | RX: 1024 bytes, TX: 256 bytes |
| Timeout de leitura | 20ms por byte |

**Fonte**: Disassembly de `vl320hw.dll` função 0x10011520 (abertura da porta serial).
DCB.StopBits = 2 confirmado na instrução `movb $0x2, 0x24(%esp)`.

**Conexão atual**: Via conversor serial-WiFi TGY Cyber WS1C (TCP 192.168.0.234:1100).

---

## 2. Visão Geral dos Protocolos

**CORREÇÃO IMPORTANTE (v2.0)**: A análise anterior confundia os protocolos dos dois
dispositivos suportados por `vl320hw.dll`. Os comandos ASCII (TST:CHECK, ACQ:START, etc.)
são **exclusivamente para o VL320** (dispositivo USB). O VQ1000 usa um **protocolo binário
ESC completamente diferente**.

O `vl320hw.dll` suporta dois dispositivos com protocolos distintos:

| Dispositivo | Interface | Protocolo | Código de tipo |
|-------------|-----------|-----------|----------------|
| **VQ1000** | RS-232 serial | **Binário ESC** (comandos `1B xx`) | 0x10010 |
| **VL320** | USB | **ASCII** (TST:CHECK, ACQ:START, etc.) via DeviceIoControl | 0x10020 |

O VQ1000 suporta **dois modos de operação**:

| Modo | Uso | Iniciado por |
|------|-----|-------------|
| **Impressora (DLE/ACK)** | Exportação de exames armazenados | Usuário no painel |
| **Comando (ESC binário)** | Controle programático (aquisição remota, config) | Software host |

**Regra crítica**: No modo impressora, enviar QUALQUER byte que não seja a sequência
de handshake correta (ACK+ESC+I) em resposta a DLE **causa desconexão imediata**
("printer offline").

---

## 3. Protocolo de Emulação de Impressora (DLE/ACK)

Este é o modo usado pelo nosso app. O Vasoquant se comporta como se estivesse
conectado a uma impressora serial térmica (Epson P40, Seiko DPU-411, etc.).

### 3.1 Handshake e Polling (idle)

```
Vasoquant → Host:  0x10 (DLE)                     ~1x/segundo
Host → Vasoquant:  0x06 0x1B 0x49 (ACK ESC 'I')   "impressora pronta" + solicitação de ID
Vasoquant → Host:  [13 bytes de identificação]      SOH + tipo + DLE + serial + fw + EOT + CR
```

**CORREÇÃO v2.0**: O disassembly da função de processamento de bytes (0x100118c0)
revelou que a resposta ao DLE não é apenas ACK (1 byte), mas **ACK + ESC + 'I' (3 bytes)**:
- Constante em 0x10016D10: `06 1B 49`
- Estado 2 da máquina de estados: detecta DLE, envia 3 bytes, transita para estado 3

A resposta de identificação (13 bytes) contém:
```
Byte 0:     Tipo de resposta (esperado: 0x01)
Bytes 5-9:  Número de série (constrói valor 32-bit)
Byte 10:    Indicador de versão do protocolo
Byte 11:    Indicador de protocolo alternativo
Bytes 12-13: Versão de firmware (BCD: major×100 + minor)
```

**Detecção de versão do protocolo** (a partir da resposta de 13 bytes):
- Se byte[10] == 0x0A e byte[11] == 0x01: **Protocolo antigo** (sem TST:CHECK)
  - Flag `extended_protocol` = 0
- Se byte[10] == 0x14 e byte[11] == 0xFF: **Protocolo estendido** (TST:CHECK capaz)
  - Flag `extended_protocol` = 1

**Nota**: Nosso app atualmente envia apenas ACK (1 byte) e funciona para receber
dados exportados. O handshake completo (3 bytes) pode ser necessário para modo de
comando ou para manter a conexão mais estável.

- Se não receber resposta → aparelho mostra "printer offline"
- O software Vasoview original usa timeouts infinitos (MAXDWORD) e modo passivo

### 3.2 Transmissão de Exame

Quando o usuário seleciona "Imprimir" no aparelho, os dados são enviados como
uma sequência de blocos (um por canal/medição):

```
┌─────────────┐                              ┌──────────┐
│  Vasoquant  │                              │   Host   │
└──────┬──────┘                              └────┬─────┘
       │                                          │
       │  ──── DLE (0x10) ──────────────────►     │  Polling
       │  ◄─── ACK (0x06) ──────────────────      │
       │       ... (repetido ~1x/segundo) ...     │
       │                                          │
       │  ════ [Bloco 1: header+dados+meta] ►     │  Exame canal 1
       │  ◄─── ACK (0x06) ──────────────────      │  OBRIGATÓRIO
       │                                          │
       │  ════ [Bloco 2: header+dados+meta] ►     │  Exame canal 2
       │  ◄─── ACK (0x06) ──────────────────      │  OBRIGATÓRIO
       │                                          │
       │       ... (mais blocos se houver) ...    │
       │                                          │
       │  ──── DLE (0x10) ──────────────────►     │  Volta ao polling
       │  ◄─── ACK (0x06) ──────────────────      │
```

**CRÍTICO**: ACK deve ser enviado após receber QUALQUER pacote de dados,
não apenas DLE. Caso contrário o aparelho mostra "offline" intermitente.

### 3.3 Testes de Protocolo (Modo Impressora)

| Byte/Comando enviado | Estando Online | Estando Offline |
|---------------------|----------------|-----------------|
| ACK (0x06) após DLE | "printer online" | — |
| ACK (0x06) espontâneo | **OFFLINE** | Sem efeito |
| NAK (0x15) | **OFFLINE** | Sem efeito |
| ENQ (0x05) | **OFFLINE** | Sem efeito |
| DLE (0x10) | **OFFLINE** | Sem efeito |
| EOT (0x04) | **OFFLINE** | Sem efeito |
| ESC (0x1B) ×2 | **OFFLINE** | Sem efeito |
| Qualquer ASCII | **OFFLINE** | Sem efeito |

---

## 4. Formato dos Pacotes de Dados

### 4.1 Estrutura Completa de um Bloco

```
 Offset  Bytes       Descrição
 ──────  ──────────  ─────────────────────────────────────
 0       1B          ESC (início de bloco)
 1       4C          'L' (marcador de label)
 2       XX          Label byte (canal/tipo da medição)
 3       04          EOT (fim do label header)
 4       01          SOH (início do header de dados)
 5       1D          GS (group separator)
 6       00          Padding
 7-8     LL HH       Número de amostras (16-bit LE)
 9...    LL HH ×N    Amostras PPG (16-bit LE cada)
 ...     [19 bytes]  Metadados (ver seção 4.3)
```

### 4.2 Labels de Canal

| Byte | Caracter | Significado | Descrição |
|------|----------|-------------|-----------|
| 0xE2 | Lâ | MID c/ Tq | Membro Inferior Direito, com Tourniquet |
| 0xE1 | Lá | MID s/ Tq | Membro Inferior Direito, sem Tourniquet |
| 0xE0 | Là | MIE c/ Tq | Membro Inferior Esquerdo, com Tourniquet |
| 0xDF | Lß | MIE s/ Tq | Membro Inferior Esquerdo, sem Tourniquet |
| 0xDE | LÞ | Canal 5 | A ser identificado |

O aparelho suporta até 8 canais em pares (UI mostra `check_Id12`, `check_Id34`,
`check_Id56`, `check_Id78`), cada par com seletor de tourniquet.

### 4.3 Metadados (Completamente Decodificados)

Os 19 bytes após as amostras contêm o baseline, número do exame e todos os
parâmetros pré-calculados pelo hardware. Verificado em 32 blocos com 100% de
acerto no peak (baseline + amplitude = samples[peak_index]).

```
 Offset  Bytes   Descrição
 ──────  ──────  ────────────────────────────────────────────
 0       1D      GS (marcador)
 1-2     BB BB   Baseline (16-bit LE, valor ADC)
 3-5     00 00 00  Separador
 6       1D      GS (marcador)
 7-8     EE EE   Número do exame (16-bit LE)
 ─── PAYLOAD (parâmetros calculados pelo hardware) ─────────
 9       TT      To_samples (distância peak→endpoint, em amostras)
 10      HH      Th_samples (amostras até 50% recuperação)
 11-12   AA AA   Amplitude (16-bit LE, peak_value − baseline)
 13-14   FF FF   Fo × 100 (16-bit LE, em 0.01 %·s)
 15      PP      Peak_raw (peak_index = PP + 2×sr − 1 = PP + 7)
 16      II      Ti (segundos, inteiro)
 17      FL      Flags (0x00 = normal, 0x80 = endpoint não detectado)
 18      04      EOT (fim do bloco)
```

**Valores derivados:**
```
peak_index  = peak_raw + 7
end_index   = peak_index + To_samples
peak_value  = baseline + amplitude        (verificado: 32/32 = 100%)
To          = To_samples / sr             (segundos)
Th          = Th_samples / sr             (segundos)
Vo          = amplitude × 100 / baseline  (%)
Fo          = Fo_x100 / 100              (%·s)
Ti          = diretamente do byte 16      (segundos)
```

**Exemplo real** (Exame #1250, MID c/ Tq):
```
1D A7 09 00 00 00 1D E2 04 87 34 A2 00 FE 1E 44 18 00 04
│  └─┬──┘         │  └─┬──┘ │  │  └┬──┘ └┬──┘ │  │  │  │
│  baseline       │  exam   │  │  ampl  Fo×100│  │  │  EOT
│  =2471          │  =1250  │  │  =162  =7934 │  │  flags=0x00
GS                GS        │  Th=52          │  Ti=24s
                            To=135 amostras   peak_raw=68
                                              → peak_idx=75

Verificação: samples[75] = 2633 = 2471 + 162 ✓
To = 135/4 = 33.8s (laudo: 34.0s, erro 0.6%)
Th = 52/4 = 13.0s  (laudo: 12.5s, erro 4.0%)
Ti = 24s            (laudo: 24s,   erro 0.0%)
Vo = 162/2471×100 = 6.6% (laudo: 6.6%, erro 0.0%)
Fo = 7934/100 = 79.3%·s  (laudo: 83%·s, erro 4.5%)
```

### 4.4 Amostras PPG

- **Formato**: 16 bits little-endian por amostra
- **Faixa típica**: 2000-3500 (ADC de 12 bits)
- **Taxa de amostragem**: 4 Hz (confirmado: 64 amostras em 16s de exercício)
- **Conversão**: %PPG = (ADC − baseline) / 27

**Nota sobre amostragem**: O hardware adquire a ~40 Hz, faz média de 5 amostras (→8 Hz),
e decima novamente para 4 Hz na exportação. Confirmado pelo comando `ACQ:SPEED/40,5,AVG,1`
encontrado em `vl320hw.dll`.

### 4.5 Artefatos no Final dos Dados

Os últimos ~3 valores de cada bloco podem ser artefatos (bytes de controle
interpretados como dados). O parser remove automaticamente outliers usando IQR.

---

## 5. Protocolo Binário ESC do VQ1000 (Modo Comando)

Protocolo binário nativo do VQ1000 para controle programático. Usa sequências
ESC (0x1B) sobre a porta serial RS-232. Completamente distinto dos comandos
ASCII do VL320.

**Fonte**: Disassembly de `vl320hw.dll`, constantes em 0x10016D00-0x10016D3F,
funções VQ1000_StartAcq (0x10013540), VQ1000_GetDeviceConfig (0x10012D30), etc.

### 5.0 Catálogo de Comandos ESC do VQ1000

| Bytes | Mnemônico | Função VQ1000_* | Descrição |
|-------|-----------|-----------------|-----------|
| `06 1B 49` | ACK ESC 'I' | (handshake) | Resposta ao DLE + solicitação de ID |
| `1B 4B 3F` | ESC K ? | GetDeviceConfig | Consultar configuração do aparelho |
| `1B 55 3F` | ESC U ? | GetDirectory | Listar exames armazenados na memória |
| `1B 43 3F` | ESC C ? | (channel query) | Consultar configuração de canais |
| `1B 43 01 00 xx 04` | ESC C + params | StartAcq (extended) | Início remoto com parâmetros |
| `1B 4D xx` | ESC M + canal | StartAcq (old) | Iniciar medição no canal xx |
| `1B 41` | ESC A | StopAcq | Parar aquisição |
| `1B 4C xx xx` | ESC L + exam# | GetAcquisition | Buscar exame (16-bit LE) |
| `1B 44` | ESC D | Disconnect | Desconectar do aparelho |
| `1B 50 01` | ESC P SOH | ClearMemory | Limpar toda a memória |
| `1B 45` | ESC E | EnableAcq | Habilitar aquisição |
| `1B 6B` | ESC k | (keep-alive) | Keep-alive remoto |

### 5.0.1 Keep-Alive Binário

O VQ1000 usa keep-alive binário (NÃO TST:CHECK):
- **SYN (0x16)**: Enviado quando não autenticado (constante em 0x10016D00)
- **ENQ (0x05)**: Enviado quando autenticado (constante em 0x10016D14)
- **Timeout**: 4 segundos (0xFA0 = 4000ms)

`VQ1000_CheckWatchdog` (0x10014680) é trivial: apenas verifica/limpa um flag booleano
interno. **NÃO envia TST:CHECK** — esse comportamento é do VL320.

### 5.0.2 Máquina de Estados da Thread de Comunicação

A thread de comunicação (0x100127C0) executa um loop principal com Sleep(20ms)
entre iterações. Cada byte recebido é processado pela função 0x100118C0.

| Estado | Valor | Descrição |
|--------|-------|-----------|
| 1 | DISCONNECTED | Desconectado |
| 2 | INITIAL | Porta aberta, aguardando primeiro handshake |
| 3 | CONNECTED | Dispositivo conectado, pronto para comandos |
| 4 | NEGOTIATING | Negociando firmware/capacidades |
| 5 | IDLE | Conectado e ocioso, watchdog ativo |
| 6 | WATCHDOG_EXPIRED | Timer de watchdog expirado |
| 7 | TX_PENDING | Dados pendentes para transmissão |
| 8 | ACQ_ACTIVE | Aquisição em andamento |
| 9 | GET_DIR | Obtendo listagem de diretório |
| 10 | GET_ACQ | Obtendo dados de aquisição |

**Loop principal** (pseudocódigo):
```
while (thread_running):
    1. Verificar timeout de resposta pendente
       - Se GetTickCount() >= deadline: desconectar
    2. Enviar dados pendentes (WriteFile)
    3. Verificar watchdog (4 segundos)
       - Estado 5 (IDLE): enviar keep-alive (SYN ou ENQ)
       - Estado 6 (WATCHDOG_EXPIRED): desconectar
    4. Ler 1 byte da serial (ReadFile, timeout 20ms)
    5. Processar byte pela máquina de estados
    6. Sleep(20ms)
```

### 5.0.3 Sequência de Inicialização

Baseado no disassembly de VQ1000_HardwareSetup (0x10012CD0) e VQ1000_GetDeviceConfig (0x10012D30):

```
1. Abrir porta serial COM (8N2, 9600 baud)
2. Iniciar thread de comunicação (0x100127c0)
3. Thread entra em loop: ler 1 byte, processar pela máquina de estados
4. Estado 2 (INITIAL): Aguardar DLE (0x10) do aparelho
5. Ao receber DLE: enviar ACK+ESC+I (06 1B 49), timeout 1000ms
6. Estado 3 (CONNECTED): Aguardar resposta de 13 bytes (identificação)
7. Detectar versão do protocolo:
   - byte[10]==0x0A, byte[11]==0x01: protocolo antigo
   - byte[10]==0x14, byte[11]==0xFF: protocolo estendido
8. Extrair serial number (bytes 5-9) e firmware version (bytes 12-13, BCD)
9. Aparelho agora está ONLINE → estado 5 (IDLE)
10. GetDeviceConfig: enviar ESC K ? (1B 4B 3F) com timeout 3000ms
```

### 5.0.4 Início de Aquisição (dois protocolos)

VQ1000_StartAcq (0x10013540) suporta dois modos:

**Protocolo antigo** (extended_protocol == 0):
```
Host → VQ1000:  1B 4D xx     (ESC M + canal)
  - Se acq_mode == 1: xx = canal + 0x32
  - Se acq_mode != 1: xx = 0x31
```

**Protocolo estendido** (extended_protocol == 1):
```
Passo 1 - Keep-alive:
Host → VQ1000:  1B 6B        (ESC k — aguarda estado IDLE)

Passo 2 - Início remoto:
Host → VQ1000:  1B 43 01 00 xx 04  (ESC C + SOH + NUL + canais + EOT)
  - byte[4] = bitmask de canais: bit 0 = canal 1, bit 1 = canal 2
  - Timeout: 1000ms

Resposta esperada (4 bytes):
  - byte[0] == 0x01: sucesso
  - byte[1]: contagem de canais
  - byte[2]: tipo de canal (0x01 ou 0x02)
  - byte[3] == 0x04: confirmação (EOT)
```

**Parar aquisição**: `1B 41` (ESC A), timeout 3000ms.
No protocolo estendido, um byte adicional é enviado: `1B 41 01` ou `1B 41 00`.

---

## 5.1 Protocolo ASCII de Comando (TST:CHECK) — SOMENTE VL320

**ATENÇÃO**: Este protocolo é **exclusivo do VL320** (dispositivo USB Vasolab 320).
Ele **NÃO funciona com o VQ1000** (serial RS-232). Enviá-lo ao VQ1000 causa
desconexão imediata.

Os comandos ASCII são enviados pelo VL320 via DeviceIoControl (IOCTL 0x222029),
encapsulados em frames DLE/SOH/STX/ETX, através de dois canais:
- Canal 0x1A8 (424): controle
- Canal 0x1B1 (433): aquisição

Protocolo alternativo para controle programático completo do VL320.
Usado pelo software Vasoview quando opera em modo "online" (aquisição em tempo real).

### 5.2 Formato de Comandos (VL320 apenas)

```
COMANDO:SUBCOMANDO/PARÂMETROS<CR>
```

- Terminador: `<CR>` (0x0D)
- Separadores: `:` entre comando e subcomando, `/` entre subcomando e parâmetros
- Resposta típica: `OK<CR>`

### 5.3 Keep-Alive e Watchdog (VL320 apenas)

```
Host → VL320:  TST:CHECK<CR>     (a cada 1-2 segundos, via DeviceIoControl)
VL320 → Host:  OK<CR>
```

Se `TST:CHECK` não for recebido por ~5 segundos:
- VL320 entra em modo watchdog
- Aquisição é interrompida automaticamente

**Nota**: O VQ1000 usa keep-alive binário SYN/ENQ (ver seção 5.0.1), NÃO TST:CHECK.

### 5.4 Sequência de Aquisição (VL320 apenas)

```
Host → VL320:  TST:CHECK<CR>       Keep-alive
VL320 → Host:  OK<CR>
        ... (repetido até estabilizar) ...
Host → VL320:  ACQ:START<CR>       Iniciar aquisição
VL320 → Host:  STARTED<CR>         Confirmação
VL320 → Host:  [dados em stream]   Dados de aquisição
Host → VL320:  ACQ:STOP<CR>        Parar aquisição
VL320 → Host:  STOPPED<CR>         Confirmação
```

### 5.5 Catálogo Completo de Comandos ASCII (VL320 apenas)

Extraído de `vl320hw.dll` via `strings`. Estes comandos são enviados ao VL320 via
DeviceIoControl, **NÃO** pela porta serial RS-232. O `%c`, `%d`, `%u`, `%s` indicam
parâmetros variáveis (caracter, inteiro, unsigned, string).

#### TST — Teste e Watchdog (VL320)

| Comando | Descrição |
|---------|-----------|
| `TST:CHECK` | Keep-alive / verificação de conexão |
| `TST:AUTH/%u` | Autenticação com código numérico |
| `TST:EXIT` | Sair do modo de teste |
| `TST:GAIN1` | Testar ganho canal 1 |
| `TST:GAIN2` | Testar ganho canal 2 |
| `TST:GAIN3` | Testar ganho canal 3 |
| `TST:OFS1` | Testar offset canal 1 |
| `TST:OFS2` | Testar offset canal 2 |

#### ACQ — Aquisição de Dados

| Comando | Descrição |
|---------|-----------|
| `ACQ:START` | Iniciar aquisição |
| `ACQ:STOP` | Parar aquisição |
| `ACQ:SPEED/%u` | Definir velocidade de aquisição (Hz) |
| `ACQ:SPEED/40` | 40 Hz |
| `ACQ:SPEED/40,5,AVG,1` | 40 Hz, média de 5, 1 canal |

#### S# — Controle de Sensores (A-F, X)

| Comando | Descrição |
|---------|-----------|
| `S#A:ON` / `S#A:OFF` | Ligar/desligar sensor A |
| `S#B:ON` / `S#B:OFF` | Sensor B |
| `S#C:ON` / `S#C:OFF` | Sensor C |
| `S#D:ON` / `S#D:OFF` | Sensor D |
| `S#E:ON` / `S#E:OFF` | Sensor E |
| `S#F:ON` / `S#F:OFF` | Sensor F |
| `S#X:OFF` | Desligar todos os sensores |
| `S#%c:ADC/AC` | Modo ADC corrente alternada |
| `S#%c:ADC/DC` | Modo ADC corrente contínua |
| `S#%c:CLK/%d` | Clock do sensor |
| `S#%c:FLT/HI` | Filtro passa-alta |
| `S#%c:FLT/LO` | Filtro passa-baixa |
| `S#%c:MIC` | Modo microfone |
| `S#%c:RFX` | Modo reflexo (D-PPG) |
| `S#%c:TRM` | Modo terminal |
| `S#PL:STD` | LED PPG modo padrão |
| `S#PL:ALT` | LED PPG modo alternado |

**Subcomandos por lado (L=esquerdo, R=direito):**

| Comando | Descrição |
|---------|-----------|
| `S#%cL:ON` / `S#%cR:ON` | Canal esquerdo/direito ON |
| `S#%cL:ACA/%d` / `S#%cR:ACA/%d` | Amplificação AC |
| `S#%cL:TXP/0` / `S#%cR:TXP/0` | Potência de transmissão zero |
| `S#%c%c:TXP/%d` | Potência TX dual-sensor |
| `S#%s:ACA/%u` | Amplificação AC (por nome) |

#### CAL — Calibração

| Comando | Descrição |
|---------|-----------|
| `CAL:EXIT` | Sair da calibração |
| `CAL:GAIN1` / `CAL:GAIN2` | Calibrar ganho |
| `CAL:OFS` | Calibrar offset |
| `CAL:S#C/LEFT` / `CAL:S#C/RIGHT` | Calibrar sensor C |

#### CSW — Controle de Manguito (Cuff Switch)

| Comando | Descrição |
|---------|-----------|
| `CSW:ON/%s` | Ligar manguito (com parâmetro) |
| `CSW:OFF/%s` | Desligar manguito |
| `CSW:LOCK` | Travar manguito |
| `CSW:UNLOCK` | Destravar manguito |

#### CRS/CSL — Velocidade e Seleção do Manguito

| Comando | Descrição |
|---------|-----------|
| `CRS:HI` | Velocidade de insuflação alta |
| `CRS:LO` | Velocidade baixa |
| `CRS:STD` | Velocidade padrão |
| `CSL:ON` / `CSL:OFF` | Seleção de manguito ON/OFF |

#### AIR — Compressor de Ar

| Comando | Descrição |
|---------|-----------|
| `AIR:ON` / `AIR:OFF` | Ligar/desligar compressor |
| `AIR:HI/%d` | Pressão alta (mmHg) |
| `AIR:LO/%d` | Pressão baixa (mmHg) |
| `AIR:REFILL` | Reencher tanque |

#### MSG — Mensagens de Status

| Comando | Descrição |
|---------|-----------|
| `MSG:STAT/0` | Status variante 0 |
| `MSG:STAT/4` | Status variante 4 |
| `MSG/TM1` | Timer 1 |

#### SYS/SVC/UPD — Sistema e Firmware

| Comando | Descrição |
|---------|-----------|
| `SYS:Vasolab 320` | Identificação do sistema |
| `SVC:001/%08X` | Código de serviço (hex) |
| `UPD:INSTALL` | Instalar firmware |
| `UPD:XPUT/%X,%X` | Transferir dados de firmware |
| `UPD:#%04u` | Progresso do update |

### 5.6 Nota sobre CFG:GET / CFG:SET

Os comandos `CFG:GET` e `CFG:SET` mencionados em versões anteriores deste documento
**NÃO foram encontrados** nas DLLs. A configuração do VQ1000 é feita via comandos
binários ESC K ? (consulta) e sequências binárias para escrita, acessados pelas
funções `VQ1000_GetDeviceConfig` (0x10012D30) e `VQ1000_SetDeviceConfig` (0x100131B0).

---

## 6. API do Hardware (`vl320hw.dll`)

Funções exportadas que revelam as capacidades do aparelho:

### 6.1 VQ1000 (D-PPG)

| Função | RVA | Comando ESC | Descrição |
|--------|-----|-------------|-----------|
| `VQ1000_HardwareSetup` | 0x12CD0 | — | Configurar baud rate (4800/9600) |
| `VQ1000_GetDeviceInfo` | 0x12C60 | — | Info do aparelho (serial, firmware) |
| `VQ1000_GetDeviceConfig` | 0x12D30 | `1B 4B 3F` | Ler configuração (timeout 3000ms) |
| `VQ1000_SetDeviceConfig` | 0x131B0 | — | Configurar aparelho |
| `VQ1000_Disconnect` | 0x134A0 | `1B 44` | Desconectar |
| `VQ1000_StartAcq` | 0x13540 | `1B 4D xx` ou `1B 43...` | Iniciar aquisição |
| `VQ1000_StopAcq` | 0x13D40 | `1B 41` | Parar aquisição (timeout 3000ms) |
| `VQ1000_ReqStopAcq` | 0x14180 | — | Solicitar parada (async) |
| `VQ1000_EnableAcq` | 0x14270 | `1B 45` | Habilitar aquisição |
| `VQ1000_GetDirectory` | 0x14290 | `1B 55 3F` | Listar exames na memória |
| `VQ1000_GetAcquisition` | 0x144C0 | `1B 4C xx xx` | Obter exame (buf min 1024) |
| `VQ1000_CheckWatchdog` | 0x14680 | — | Verifica/limpa flag (NÃO envia nada) |
| `VQ1000_StartCharging` | 0x146A0 | — | Carregar bateria |
| `VQ1000_ClearMemory` | 0x14790 | `1B 50 01` | Limpar memória |
| `VQ1000_FinalizeRemoteStart` | 0x14870 | — | Finalizar início remoto |

### 6.2 VL320 (Vasolab — funções de pressão/Doppler)

| Função | Descrição |
|--------|-----------|
| `VL320_Startup` / `Shutdown` | Liga/desliga |
| `VL320_ActivateSensor` / `DeactivateSensor` | Ativar/desativar sensor |
| `VL320_CalibrateSensor` | Calibrar sensor |
| `VL320_GetFirmwareVersion` | Versão do firmware |
| `VL320_GetSerialNo` | Número de série |
| `VL320_OnlineStatus` | Status online |
| `VL320_SetSensorFilter` | Filtro (HI/LO) |
| `VL320_SetSensorGainAC` / `DC` | Ganho AC/DC |
| `VL320_SetSensorSampling` | Taxa de amostragem |
| `VL320_SetSensorPower` | Potência do sensor |
| `VL320_SetPressure` / `GetPressure` | Pressão do manguito |
| `VL320_SetAirSupply` | Compressor de ar |
| `VL320_StartFirmwareUpdate` | Atualizar firmware |

---

## 7. Configuração do Aparelho

### 7.1 Arquivo INI (`vq1000.ini`)

Chaves relevantes encontradas nas DLLs:

| Seção / Chave | Descrição |
|---------------|-----------|
| `Hardware/VQ1000com` | Porta COM (ex: 2 para COM2) |
| `Hardware/VQ1000bps` | Baud rate (1=4800, 2=9600) |
| `Application_DPPG/VQ1000Zoom` | Zoom na visualização (true/false) |
| `Application_DPPG/DualChannel` | Modo dual channel (true/false) |
| `USER_GUIDANCE/RightLeft` | Ordem de medição dir/esq |

### 7.2 Opções de Configuração (de `dppg 2.dll`)

#### Impressora Serial

| Valor | Modelo |
|-------|--------|
| 1 | Epson P40 (térmica) |
| 2 | Epson P40, sem impressão durante exercício |
| 3 | Epson matricial (dot-matrix) |
| 4 | Canon BJ10sx (jato de tinta) |
| 5 | HP LaserJet / DeskJet |
| 6 | Seiko DPU-411 (térmica) |

#### Formato de Impressão

| Valor | Descrição |
|-------|-----------|
| 1 | Relatório curto |
| 2 | Relatório padrão |
| 3 | 2 aquisições por página (A4/Letter) |
| 4 | 4 aquisições por página (A4/Letter) |

#### Parâmetros Exibidos

| Valor | Descrição |
|-------|-----------|
| 1 | Apenas parâmetros-chave (To, Vo) |
| 2 | Todos os parâmetros (To, Th, Ti, Vo, Fo) |

#### Faixa de Amplitude

| Valor | Descrição |
|-------|-----------|
| 1 | Padrão (Vo máx. 20%) |
| 2 | Estendida (Vo máx. 40%) |

#### Detecção de Estado Estável (Baseline)

| Valor | Descrição |
|-------|-----------|
| 1 | Automática, início em até 40s |
| 2 | Sem detecção, início em até 30s |
| 3 | Sem detecção, início imediato |

#### Rotina de Exercício

| Valor | Descrição |
|-------|-----------|
| 1 | 8 movimentos em 16 segundos |
| 2 | 10 movimentos em 15 segundos |

#### Início da Gravação

| Valor | Descrição |
|-------|-----------|
| 1 | 3 segundos antes do exercício |
| 2 | No início do exercício |

#### Som

| Valor | Descrição |
|-------|-----------|
| 1 | Volume normal |
| 2 | Volume aumentado |
| 3 | Sem metrônomo, sem som durante refilling |
| 4 | Sem som durante refilling |

#### Memória de Aquisição

| Valor | Capacidade |
|-------|-----------|
| 1 | 10 aquisições |
| 2 | 20 aquisições |
| 3 | 50 aquisições |

#### Tourniquet

Opções: Sem tourniquet, Manual, Tourniquet 1/2/3, Posição do tourniquet.

#### Modo Demo

| Valor | Descrição |
|-------|-----------|
| 1 | Menu demo desligado |
| 2 | Menu demo ligado |
| 3 | Exame simulado (demonstração para paciente) |

---

## 8. Caracteres de Controle

| Hex | Nome | Descrição |
|-----|------|-----------|
| 0x01 | SOH | Start of Header — início do header de dados |
| 0x02 | STX | Start of Text — início de pacote VL320 |
| 0x03 | ETX | End of Text — fim de pacote VL320 |
| 0x04 | EOT | End of Transmission — fim de bloco |
| 0x05 | ENQ | Enquiry |
| 0x06 | ACK | Acknowledge — confirmação (host envia) |
| 0x0D | CR | Carriage Return — terminador de comandos ASCII |
| 0x10 | DLE | Data Link Escape — polling de impressora |
| 0x15 | NAK | Negative Acknowledge |
| 0x1B | ESC | Escape — início de label/comando |
| 0x1D | GS | Group Separator — marcador de metadados |

---

## 9. Parâmetros Clínicos

### 9.1 Definições

| Parâmetro | Símbolo | Unidade | Descrição |
|-----------|---------|---------|-----------|
| Venous refilling time | To | s | Tempo de reenchimento venoso |
| Venous half ampl. time | Th | s | Tempo de meia amplitude |
| Initial inflow time | Ti | s | Tempo de influxo inicial |
| Venous pump power | Vo | % | Potência da bomba venosa |
| Venous pump capacity | Fo | %·s | Capacidade da bomba venosa |

### 9.2 Fórmulas (confirmadas via engenharia reversa de `dppg 2.dll`)

```
Vo = (peak_value − baseline) / baseline × 100
Th = tempo até (peak − baseline) cair a 50%  (threshold crossing)
Ti = extrapolação linear adaptativa (janela 3s ou 6s, NÃO é threshold)
To = tempo até retorno ao baseline (97% de recuperação, ou markers do HW)
Fo = integral da curva de recuperação com correção trapezoidal (NÃO é Vo×Th)
```

### 9.3 Taxa de Amostragem

- **4 Hz** (confirmado: 64 amostras em 16s de exercício)
- Hardware adquire a ~40 Hz, decima com média de 5 → 8 Hz, e decima novamente → 4 Hz
- Conversão ADC → %PPG: fator ≈ 27 unidades ADC por %

---

## 10. Diagrama de Estados

```
                    ┌──────────────┐
                    │   OFFLINE    │
                    └──────┬───────┘
                           │ Host conecta TCP
                           ▼
                    ┌──────────────┐
            ┌──────│  AGUARDANDO  │◄────────────────┐
            │      │    DLE       │                  │
            │      └──────┬───────┘                  │
            │             │ Recebe DLE (0x10)        │
            │             ▼                           │
            │      ┌──────────────┐                  │
            │      │  ONLINE      │──── timeout ─────┘
            │      │  (printer    │
            │      │   online)    │
            │      └──────┬───────┘
            │             │ Usuário exporta exame
            │             ▼
            │      ┌──────────────┐
            │      │  RECEBENDO   │
            │      │  DADOS       │◄──┐
            │      │  (blocos)    │   │ ACK após cada bloco
            │      └──────┬───────┘───┘
            │             │ Todos os blocos recebidos
            └─────────────┘  (volta ao polling DLE)
```

---

## 11. Referências

- **Aparelho**: [Elcat Vasoquant 1000 D-PPG](https://www.elcat.de)
- **Conversor Serial-WiFi**: [TGY Cyber WS1C](https://www.tgycyber.com/pt-BR/docs/ws1c)
- **Software original**: Vasoview/VASOSCREEN v1.04 (February 2017)
- **DLLs analisadas**: `dppg 2.dll` (cálculos), `vl320hw.dll` (comunicação serial)

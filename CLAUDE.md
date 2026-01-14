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

O Vasoquant usa um protocolo baseado em impressora serial:

### Handshake
1. Aparelho envia **DLE (0x10)** periodicamente para verificar se "impressora" está online
2. Devemos responder com **ACK (0x06)** para indicar que estamos prontos
3. Se não respondermos, aparelho mostra "printer offline"

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

## Estrutura do Projeto

```
dppg/
├── CLAUDE.md           # Esta documentação
├── dppg_reader.py      # Aplicativo principal com GUI
└── ppg_data_*.csv      # Arquivos de dados exportados
```

## Formato do CSV Exportado

```csv
sample_index,value
0,2471
1,2472
...
```

## Problemas Conhecidos

1. **Parser de dados**: Atualmente extrai amostras baseado na faixa de valores (2000-3500), pode incluir alguns bytes espúrios
2. **Múltiplos canais**: O aparelho pode enviar múltiplos blocos (Lâ, Lá, etc.) que não estão sendo separados

## TODO

- [ ] Parsear corretamente o protocolo (separar header, dados, metadados)
- [ ] Identificar e separar diferentes canais/medições
- [ ] Extrair metadados (data, hora, número do exame, etc.)
- [ ] Melhorar visualização do gráfico PPG
- [ ] Salvar em formato mais estruturado (JSON com metadados)
- [ ] Documentar significado dos diferentes labels (Lâ, Lá, etc.)

## Referências

- Elcat Vasoquant 1000: https://www.elcat.de/wp-content/uploads/a2101-9311_vq1000.d-ppg_prospekt_de.pdf
- Conversor WS1C: https://www.tgycyber.com/pt-BR/docs/ws1c

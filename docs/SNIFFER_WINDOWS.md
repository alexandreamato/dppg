# Serial Sniffer - Guia para Windows 7

Intercepta a comunicação entre o Vasoquant 1000 e o software Vasoview original.

## Requisitos

1. **Python 3** - https://www.python.org/downloads/
   - Durante instalação, marque "Add Python to PATH"

2. **pyserial** - Instalado automaticamente pelo batch file
   ```
   pip install pyserial
   ```

3. **com0com** (apenas para modo proxy) - https://sourceforge.net/projects/com0com/
   - Cria pares de portas seriais virtuais

## Modo 1: PASSIVO (mais simples)

Escuta diretamente a porta onde o Vasoquant está conectado.

```
                    ┌─────────────┐
   Vasoquant ──────►│   Sniffer   │──────► Log
     COM2           │  (escuta)   │
                    └─────────────┘
```

### Como usar:
1. Desconecte o Vasoview do COM2
2. Execute: `python serial_sniffer.py --listen COM2`
3. Exporte exames no Vasoquant
4. Dados são logados

**Limitação**: Não captura as respostas do software original.

## Modo 2: PROXY (recomendado)

Intercepta comunicação bidirecional entre Vasoquant e Vasoview.

```
                    ┌─────────────┐
   Vasoquant ──────►│   Sniffer   │◄────── Vasoview
     COM2           │   (proxy)   │         COM10
                    └─────────────┘
                          │
                          ▼
                        Log
```

### Configuração com0com:

1. Instale com0com
2. Abra "Setup Command Prompt" do com0com
3. Execute:
   ```
   install PortName=COM10 PortName=COM11
   ```
4. Isso cria um par virtual: COM10 ⟷ COM11

### Como usar:

1. Configure Vasoview para usar **COM10** (em vez de COM2)
2. Execute o sniffer:
   ```
   python serial_sniffer.py --proxy COM2 COM11
   ```
3. Inicie o Vasoview
4. Exporte exames no Vasoquant
5. Toda comunicação é logada!

## Arquivos de Saída

O sniffer cria 3 arquivos:

| Arquivo | Conteúdo |
|---------|----------|
| `serial_capture_YYYYMMDD_HHMMSS.log` | Log legível com hex e ASCII |
| `serial_capture_YYYYMMDD_HHMMSS_rx.bin` | Dados brutos RX (do dispositivo) |
| `serial_capture_YYYYMMDD_HHMMSS_tx.bin` | Dados brutos TX (do software) |

## Exemplo de Saída

```
[     0.000s] RX <<< [  1] 10 (DLE)
[     0.001s] TX >>> [  1] 06 (ACK)
[     5.234s] RX <<< [  3] 1B 4C E2 (ESC)
             ASCII: .L.
[     5.235s] TX >>> [  1] 06 (ACK)
[     5.250s] RX <<< [507] 04 01 1D 00 FA 00 A7 09 A8 09...
```

## Comandos

```bash
# Listar portas disponíveis
python serial_sniffer.py --list

# Modo passivo
python serial_sniffer.py --listen COM2

# Modo proxy
python serial_sniffer.py --proxy COM2 COM11

# Com baudrate diferente
python serial_sniffer.py --listen COM2 --baud 19200

# Salvar logs em pasta específica
python serial_sniffer.py --listen COM2 --output C:\logs
```

## Ou use o batch file

Simplesmente execute:
```
sniffer_windows.bat
```

E siga o menu interativo.

## Troubleshooting

### "Porta COM2 não encontrada"
- Verifique no Gerenciador de Dispositivos qual porta o conversor USB-Serial está usando

### "Permissão negada"
- Feche o Vasoview antes de usar modo passivo
- Execute como Administrador se necessário

### "com0com não cria portas"
- Instale com privilégios de Administrador
- Reinicie o computador após instalação

### Dados aparecem corrompidos
- Verifique baudrate (deve ser 9600)
- Verifique configuração 8N1

# Captura Serial no Windows 7 - Guia Simplificado

## Opção 1: Portmon (MAIS FÁCIL - Recomendado!)

O Portmon da Microsoft/Sysinternals captura comunicação serial **sem modificar nada**.

### Download:
https://docs.microsoft.com/en-us/sysinternals/downloads/portmon

Ou diretamente:
https://download.sysinternals.com/files/PortMon.zip

### Como usar:
1. Extraia o zip
2. Execute `portmon.exe` **como Administrador**
3. Menu: Capture → Ports → selecione COM2 (ou a porta do Vasoquant)
4. Menu: Capture → Start Capturing (Ctrl+E)
5. Abra o Vasoview normalmente e exporte exames
6. Toda comunicação aparece no Portmon!
7. Menu: File → Save para salvar o log

### Vantagens:
- Não precisa de portas virtuais
- Não interfere na comunicação
- Captura tudo (TX e RX)
- Funciona no Windows 7

---

## Opção 2: com0com com portas baixas (COM3/COM4)

### Passo a passo:

1. **Desinstale** com0com se já instalou

2. **Reinstale** como Administrador

3. Abra **"Setup Command Prompt"** do com0com (como Admin)

4. Execute:
```
remove 0
remove 1
install PortName=COM3 PortName=COM4
```

5. Verifique:
```
list
```
Deve mostrar: `COM3 <-> COM4`

### Se COM3/COM4 estiverem em uso:

Veja no Gerenciador de Dispositivos quais portas estão livres.

Para forçar remoção de porta fantasma:
1. Gerenciador de Dispositivos
2. Menu: Exibir → Mostrar dispositivos ocultos
3. Expanda "Portas (COM e LPT)"
4. Remova portas não usadas

### Configurar Vasoview:

1. Configure Vasoview para usar **COM3**
2. Execute o sniffer: `python serial_sniffer.py --proxy COM2 COM4`
3. O fluxo fica:
   ```
   Vasoquant (COM2) ←→ Sniffer ←→ COM4 ←→ COM3 ←→ Vasoview
   ```

---

## Opção 3: Serial Port Monitor (comercial, mas tem trial)

- Eltima Serial Port Monitor: https://www.eltima.com/products/serial-port-monitor/
- Free Serial Port Monitor: https://www.oyksoft.com/free-serial-port-monitor.html

Estes funcionam igual ao Portmon mas com interface melhor.

---

## Opção 4: Captura direta sem Vasoview

Se o objetivo é apenas entender o protocolo, podemos capturar **só o que o Vasoquant envia**:

1. Desconecte o Vasoview
2. Conecte apenas o conversor USB-Serial
3. Execute nosso sniffer em modo passivo:
   ```
   python serial_sniffer.py --listen COM2
   ```
4. No Vasoquant, tente exportar exames
5. O sniffer responde ACK automaticamente
6. Você vê exatamente o que o dispositivo envia

**Limitação**: Não vemos as respostas do Vasoview, mas vemos toda a estrutura de dados.

---

## Resumo - O que recomendo:

| Objetivo | Melhor opção |
|----------|--------------|
| Ver comunicação completa sem complicação | **Portmon** |
| Interceptar e modificar dados | com0com + sniffer proxy |
| Apenas ver o que Vasoquant envia | sniffer modo passivo |

## Troubleshooting

### "Porta em uso"
- Feche o Vasoview antes de abrir o sniffer
- Ou use Portmon que não trava a porta

### "com0com não cria COM3"
- Execute como Administrador
- Verifique se COM3 não está em uso (Gerenciador de Dispositivos)
- Tente: `install - PortName=COM3`

### "Vasoview não conecta na porta virtual"
- Algumas portas virtuais precisam de configuração extra
- No com0com, tente: `change CNCA0 EmuBR=yes EmuOverrun=yes`

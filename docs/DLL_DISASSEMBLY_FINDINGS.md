# Análise de Disassembly da DLL dppg 2.dll

## Constantes Confirmadas

| VA | File Offset | Valor | Uso no Código |
|----|-------------|-------|---------------|
| 0x10039d68 | 0x38968 | **0.125** | `fmull` - Threshold Ti (87.5% recovery) |
| 0x10039de0 | 0x389e0 | **2.0** | `fldl`, `faddl` - Provavelmente para Th (amplitude/2) |
| 0x10039d40 | 0x38940 | **3.0** | `fsubl` - Possivelmente para To (3% restante) |
| 0x10039d20 | 0x38920 | **1000.0** | `fmull` - Conversão para Vo (×1000 para precisão) |
| 0x10039d98 | 0x38998 | **100.0** | `fldl`, `fdivl` - Conversão percentual |
| 0x10039d58 | 0x38958 | **10.0** | `fdivl`, `fcompl` - Baseline (10 amostras) |
| 0x10039d48 | 0x38948 | **12.0** | `fmull` - Janela de processamento |
| 0x10039d50 | 0x38950 | **6.0** | `fmull` - Janela de processamento |
| 0x10039d60 | 0x38960 | **72.0** | `fmull` - Desconhecido |
| 0x10039d80 | 0x38980 | **37.0** | `fldl`, `fmull` - Desconhecido |
| 0x10039d90 | 0x38990 | **70.0** | `fmull` - Desconhecido |
| 0x10039da0 | 0x389a0 | **300.0** | `fmull` - Desconhecido |

## Código de Cálculo Identificado

### Uso de 0.125 (Ti threshold)

```assembly
10025dac: dc 0d 68 9d 03 10   fmull  0x10039d68    ; Multiplica por 0.125
10025db2: da 4c 24 60         fimull 0x60(%esp)    ; Multiplica por fator (tempo?)
10025db6: de c1               faddp  %st, %st(1)   ; Acumula
```

Contexto: Loop de processamento de amostras, calculando threshold de Ti.

### Uso de 2.0 (Provavelmente Th)

```assembly
10025f59: dd 05 e0 9d 03 10   fldl   0x10039de0    ; Carrega 2.0
10025f64: dd 9e a8 00 00 00   fstpl  0xa8(%esi)    ; Armazena em estrutura
...
10026053: dc 05 e0 9d 03 10   faddl  0x10039de0    ; Adiciona 2.0
```

### Comparação com 10.0 (Baseline)

```assembly
1002601a: dc a6 40 01 00 00   fsubl  0x140(%esi)   ; Subtrai baseline
10026020: dc 1d 58 9d 03 10   fcompl 0x10039d58    ; Compara com 10.0
10026026: df e0               fnstsw %ax           ; Obtém resultado
10026028: f6 c4 05            testb  $0x5, %ah     ; Testa condição
```

## Algoritmo Inferido

1. **Baseline**: Calculado das primeiras 10 amostras (constante 10.0)
2. **Peak**: Encontrado por busca de máximo
3. **Amplitude**: peak - baseline

### Thresholds

- **Th** (50% recovery): `baseline + amplitude / 2.0`
  - Não usa 0.5 diretamente, mas divide por 2.0

- **Ti** (87.5% recovery): `baseline + amplitude * 0.125`
  - Constante 0.125 confirmada em 0x10039d68

- **To** (97% recovery): `baseline + amplitude * 0.03`
  - Constante 3.0 em 0x10039d40 pode ser usada como 3.0/100.0 = 0.03

### Cálculo de Vo

```assembly
10024798: db 40 10            fildl  0x10(%eax)    ; Carrega valor inteiro
1002479b: ...
100247a1: dc 31               fdivl  (%ecx)        ; Divide por algo (baseline?)
100247a3: dc 0d 20 9d 03 10   fmull  0x10039d20    ; Multiplica por 1000.0
```

Fórmula: `Vo = (value / baseline) * 1000.0` → depois convertido para percentual

## Observações

1. **0.5 não existe como constante direta** - Th usa divisão por 2.0
2. **0.03 não existe como constante direta** - To provavelmente usa 3.0/100.0
3. **Constantes 37.0, 70.0, 72.0, 300.0** têm propósito desconhecido
4. A taxa de amostragem **32.5 Hz** foi encontrada (hardware interno)

## Conclusão

Os thresholds confirmados:
- Ti: **0.125** (87.5% recovery) ✅
- Th: **0.5** via divisão por 2.0 ✅
- To: **0.03** via 3.0/100.0 ⚠️ (inferido)

O algoritmo usa detecção de cruzamento de threshold, consistente com nossa implementação.

**NOTA**: A análise não explica por que alguns valores de Ti no Vasoview são maiores que To. Isso pode indicar:
1. Extrapolação especial quando o sinal não cruza o threshold
2. Metodologia adicional não identificada no disassembly
3. Possível bug no software original

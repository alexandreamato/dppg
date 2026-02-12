# Análise de Extrapolação do Ti no Vasoview

## Problema Identificado

36.7% dos casos no banco de dados Vasoview têm **Ti > To**, o que é fisicamente impossível se ambos forem calculados por cruzamento de threshold a partir do mesmo ponto inicial.

## Evidências da Análise

### 1. Distribuição de Ti no Banco Vasoview
```
Total de medições: 532
Ti <= 20s: 239 (44.9%)
Ti <= 40s: 417 (78.4%)
Ti <= 60s: 483 (90.8%)
Ti <= 100s: 512 (96.2%)
Ti = 120s: 15 (2.8%) - VALOR MÁXIMO/SATURAÇÃO
```

### 2. Duração dos Exames
- Duração típica: 40-62 segundos (150-250 amostras a 4 Hz)
- Ti = 120s é MAIOR que qualquer duração de exame
- **Conclusão**: Ti = 120s é definitivamente extrapolado, não medido

### 3. Casos Anômalos (Ti > To)
```
Casos normais (Ti <= To): 337
Casos anômalos (Ti > To): 195 (36.7%)
```

Exemplos extremos:
- Vo=4.1%, To=22s, Ti=120s (diff=98s)
- Vo=2.4%, To=27s, Ti=116s (diff=89s)

## Thresholds Confirmados (Disassembly da DLL)

| Parâmetro | Threshold | Constante na DLL |
|-----------|-----------|------------------|
| **To** | 97% recovery (3% restante) | 0.03 via 3.0/100.0 |
| **Th** | 50% recovery | 0.50 (via 2.0 divisor) |
| **Ti** | 87.5% recovery (12.5% restante) | 0.125 @ 0x10039d68 |

## Teoria da Extrapolação

Quando o sinal **não cruza o threshold de Ti** dentro da duração da gravação:

1. O Vasoview calcula o **slope de recuperação** dos últimos pontos
2. Usa **extrapolação linear** para estimar quando o threshold seria cruzado
3. Aplica um **limite máximo de 120 segundos**

### Pseudocódigo Inferido

```python
def calculate_Ti(samples, threshold_level, peak_idx, sampling_rate=4.0):
    recovery = samples[peak_idx:]

    # Try direct crossing detection
    for i in range(len(recovery) - 1):
        if recovery[i] >= threshold_level and recovery[i + 1] < threshold_level:
            # Interpolate exact crossing
            frac = (recovery[i] - threshold_level) / (recovery[i] - recovery[i + 1])
            return (i + frac) / sampling_rate

    # No crossing found - EXTRAPOLATE
    # Calculate slope from last N points
    N = min(10, len(recovery) // 2)
    last_points = recovery[-N:]
    slope = (last_points[-1] - last_points[0]) / (N - 1)  # samples per unit

    if slope >= 0:
        # Signal not decreasing - cannot extrapolate
        return 120.0  # Maximum value

    # Extrapolate: when will signal reach threshold?
    remaining = recovery[-1] - threshold_level
    additional_samples = remaining / abs(slope)
    additional_time = additional_samples / sampling_rate

    total_time = len(recovery) / sampling_rate + additional_time

    # Cap at 120 seconds
    return min(total_time, 120.0)
```

## Impacto no Nosso Algoritmo

### Atual (sem extrapolação)
- Retorna `None` quando não há cruzamento
- Não reproduz comportamento do Vasoview

### Proposta (com extrapolação)
- Implementar extrapolação linear
- Aplicar cap de 120 segundos
- Marcar valores extrapolados com flag

## Por que Ti > To é possível?

1. **Thresholds diferentes**:
   - Ti usa `reference_baseline + amplitude * 0.125`
   - To usa `reference_baseline + amplitude * 0.03`

2. **Reference baseline pode ser diferente**:
   - Se `stable_baseline > initial_baseline`, o Ti pode ter threshold MAIOR que To
   - Isso significa que Ti pode nunca ser cruzado enquanto To é cruzado

3. **Extrapolação**:
   - Ti pode ser extrapolado para além do final da gravação
   - To pode ser medido diretamente (cruzamento encontrado)

## Recomendações

1. **Implementar extrapolação linear** para Ti quando não há cruzamento
2. **Adicionar flag** indicando se valor foi extrapolado
3. **Limitar Ti a 120s** como o Vasoview faz
4. **Para To**: também implementar extrapolação se necessário

## Constantes a Verificar na DLL

- 120.0 ou valor equivalente para cap de Ti
- Janela de pontos para cálculo de slope (provavelmente 10 amostras)
- Possível uso de 0.9701 para To (97% recovery exato)

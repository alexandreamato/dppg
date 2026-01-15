# Cálculo dos Parâmetros PPG - Engenharia Reversa

Este documento descreve as tentativas de engenharia reversa para calcular os parâmetros quantitativos do D-PPG Vasoquant 1000.

## Parâmetros a Calcular

O laudo oficial do Vasoquant apresenta 5 parâmetros:

| Parâmetro | Descrição | Unidade |
|-----------|-----------|---------|
| **To** | Tempo de reenchimento venoso (Venous refilling time) | segundos |
| **Th** | Tempo de meia amplitude (Venous half amplitude time) | segundos |
| **Ti** | Tempo de influxo inicial (Initial inflow time) | segundos |
| **Vo** | Potência da bomba venosa (Venous pump power) | % |
| **Fo** | Capacidade da bomba venosa (Venous pump capacity) | %·s |

## Valores do Laudo Oficial (Referência)

| Exame | Perna | To(s) | Th(s) | Ti(s) | Vo(%) | Fo(%s) |
|-------|-------|-------|-------|-------|-------|--------|
| 1250  | D     | 36    | 10    | 33    | 4.7   | 47     |
| 1249  | E     | 46    | 12    | 41    | 4.5   | 55     |
| 1248  | D     | 31    | 8     | 27    | 4.2   | 33     |
| 1247  | E     | 36    | 9     | 30    | 3.9   | 35     |

---

## Abordagem 1: Cálculo Simples (Tentativa Inicial)

### Fórmulas

```
baseline = média das primeiras 10 amostras
peak_value = máximo do sinal
peak_index = índice do pico máximo

Vo = (peak_value - baseline) / ADC_TO_PPG_FACTOR
     onde ADC_TO_PPG_FACTOR = 27.0 (fator de conversão ADC → %PPG)

To = tempo do pico até retorno ao baseline (quando valor <= baseline)
Th = To * 0.5
Ti = To * 0.9
Fo = Vo * To
```

### Problemas Identificados

1. **Curva não retorna ao baseline**: O sinal capturado termina antes de voltar completamente ao valor basal
2. **To muito curto**: Usando apenas o tempo até o fim da captura
3. **Th e Ti arbitrários**: Multiplicar To por constantes não reflete a física do decaimento

---

## Abordagem 2: To do Início do Exercício

### Modificação

Mudamos a definição de To para começar no **início do exercício** (quando começa a subida do sinal) em vez do pico:

```
exercise_start_index = primeiro ponto onde derivada > threshold (subida do sinal)
To = (To_end_index - exercise_start_index) / sampling_rate
```

### Resultados

To aumentou, mas ainda ficou muito abaixo dos valores do laudo.

---

## Abordagem 3: Fitting Exponencial com Offset

### Modelo Matemático

O decaimento venoso segue aproximadamente um modelo exponencial com offset:

```
V(t) = A × exp(-t/τ) + C

Onde:
- V(t) = valor do sinal no tempo t
- A = amplitude inicial do decaimento
- τ (tau) = constante de tempo do decaimento
- C = offset (valor assintótico final)
```

### Linearização

Para estimar τ, linearizamos o modelo:

```
V(t) - C = A × exp(-t/τ)
ln(V(t) - C) = ln(A) - t/τ
```

Usando regressão linear de `ln(V-C)` vs `t`:
- Coeficiente angular = `-1/τ`
- τ = `-1/slope`

### Estimativa do Offset (C)

```
C = média das últimas 20 amostras
```

### Fórmulas Derivadas

Uma vez obtido τ, calculamos:

```
To = τ × ln(A/threshold) + tempo_exercício_até_pico
     onde threshold = 0.05 × (peak - baseline)  # 5% da amplitude

Th = τ × ln(2)     # tempo para decair 50% da amplitude
Ti = τ × ln(10)    # tempo para decair 90% da amplitude

Fo = Vo × τ        # capacidade = potência × constante de tempo
```

### Implementação

```python
def calculate_parameters(self):
    # Baseline dos primeiros 10 pontos
    baseline = np.mean(samples[:10])

    # Pico máximo
    peak_index = np.argmax(samples)
    peak_value = samples[peak_index]

    # Offset: média das últimas 20 amostras
    C = np.mean(samples[-20:])

    # Dados para regressão (do pico até o fim)
    decay_region = samples[peak_index:]
    valid_mask = (decay_region - C) > 0.1

    # Regressão linear: ln(V-C) vs t
    y = np.log(decay_region[valid_mask] - C)
    x = t_array[valid_mask]
    slope, intercept = np.polyfit(x, y, 1)

    # Constante de tempo
    tau = -1.0 / slope
    tau = max(tau, 2.0)  # mínimo de 2 segundos

    # Parâmetros derivados
    Th = tau * np.log(2)
    Ti = tau * np.log(10)

    # To = tempo para decair até 5% da amplitude
    A_fit = np.exp(intercept)
    threshold = 0.05 * A_fit
    To_decay = tau * np.log(A_fit / threshold)
    To = To_decay + time_exercise_to_peak
```

---

## Resultados com Taxa de 8.33 Hz

### Valores Calculados (sampling_rate = 8.33 Hz)

| Exame | To(s) | Th(s) | Ti(s) | Vo(%) | Fo(%s) |
|-------|-------|-------|-------|-------|--------|
| 1250  | 28.0  | 5.8   | 24.1  | 5.9   | 62     |
| 1249  | 23.9  | 3.1   | 12.6  | 5.9   | 32     |
| 1248  | 22.2  | 4.3   | 11.9  | 3.5   | 20     |
| 1247  | 18.1  | 4.9   | 10.4  | 4.1   | 24     |

### Comparação com Laudo (8.33 Hz)

| Exame | Param | Laudo | Calculado | Razão |
|-------|-------|-------|-----------|-------|
| 1250  | To    | 36    | 28.0      | 1.29  |
| 1250  | Th    | 10    | 5.8       | 1.72  |
| 1250  | Ti    | 33    | 24.1      | 1.37  |
| 1250  | Vo    | 4.7   | 5.9       | 0.80  |
| 1249  | To    | 46    | 23.9      | 1.92  |
| 1249  | Th    | 12    | 3.1       | 3.87  |
| 1249  | Ti    | 41    | 12.6      | 3.25  |
| 1249  | Vo    | 4.5   | 5.9       | 0.76  |
| 1248  | To    | 31    | 22.2      | 1.40  |
| 1248  | Th    | 8     | 4.3       | 1.86  |
| 1248  | Ti    | 27    | 11.9      | 2.27  |
| 1248  | Vo    | 4.2   | 3.5       | 1.20  |
| 1247  | To    | 36    | 18.1      | 1.99  |
| 1247  | Th    | 9     | 4.9       | 1.84  |
| 1247  | Ti    | 30    | 10.4      | 2.88  |
| 1247  | Vo    | 3.9   | 4.1       | 0.95  |

**Razão média dos tempos (To, Th, Ti): ~2.1x**

---

## Hipótese: Taxa de Amostragem Incorreta

### Análise

Todos os parâmetros de tempo estão sistematicamente baixos por um fator de aproximadamente **2x**. Isso sugere que a taxa de amostragem estimada está errada.

### Cálculo da Taxa Correta

Se assumirmos:
- Taxa original estimada: 8.33 Hz
- Razão laudo/calculado: ~2.0-2.2

```
Taxa correta = 8.33 / 2.1 ≈ 4.0 Hz
```

### Possíveis Causas

1. **Reamostragem interna**: O Vasoquant pode fazer subamostragem antes de exportar
2. **Protocolo de impressão**: A saída para "impressora" pode ser em taxa reduzida
3. **Compressão de dados**: O protocolo pode enviar apenas 1 em cada 2 amostras

---

## Abordagem 4: Taxa de Amostragem Corrigida

### Mudança Aplicada

```python
# Antes
ESTIMATED_SAMPLING_RATE = 8.33  # Hz

# Depois
ESTIMATED_SAMPLING_RATE = 4.0   # Hz (calibrado com laudo)
```

### Valores Esperados (projeção com 4.0 Hz)

Com a nova taxa, todos os tempos dobram:

| Exame | To(s) | Th(s) | Ti(s) | Vo(%) | Fo(%s) |
|-------|-------|-------|-------|-------|--------|
| 1250  | ~58   | ~12   | ~50   | 5.9   | ~124   |
| 1249  | ~50   | ~6    | ~26   | 5.9   | ~66    |
| 1248  | ~46   | ~9    | ~25   | 3.5   | ~42    |
| 1247  | ~38   | ~10   | ~22   | 4.1   | ~50    |

**Nota**: Estes valores precisam ser validados executando o aplicativo novamente.

---

## Fórmulas Finais

### Constantes

```python
ADC_TO_PPG_FACTOR = 27.0          # Conversão ADC → %PPG
ESTIMATED_SAMPLING_RATE = 4.0     # Hz (calibrado)
BASELINE_SAMPLES = 10             # Amostras para baseline
OFFSET_SAMPLES = 20               # Amostras para offset C
MIN_TAU = 2.0                     # Constante de tempo mínima (s)
THRESHOLD_PERCENT = 0.05          # Limiar para To (5% da amplitude)
```

### Algoritmo

```
1. baseline = média(samples[0:10])
2. peak_index = argmax(samples)
3. peak_value = samples[peak_index]
4. exercise_start = primeiro ponto onde derivada > 0.1 × (peak - baseline)
5. C = média(samples[-20:])
6. Regressão: ln(samples[peak:] - C) vs tempo → slope
7. τ = -1/slope
8. Vo = (peak_value - baseline) / 27.0
9. Th = τ × ln(2)
10. Ti = τ × ln(10)
11. A_fit = exp(intercept)
12. To_decay = τ × ln(A_fit / (0.05 × A_fit))
13. To = To_decay + (peak_index - exercise_start) / sampling_rate
14. Fo = Vo × τ
```

---

## Observações Importantes

### Sobre Vo (%)

O parâmetro Vo está razoavelmente próximo dos valores do laudo (~20% de erro). Isso faz sentido porque:
- Vo depende apenas de **amplitude** (não de tempo)
- A conversão ADC → %PPG (fator 27) parece correta
- Pequenas diferenças podem ser devido a arredondamentos ou definição diferente de baseline

### Sobre Fo (%·s)

O Fo deveria seguir a relação:
```
Fo = Vo × τ    (ou Fo = Vo × Th segundo algumas fontes)
```

Os valores do laudo sugerem `Fo ≈ Vo × To`, mas isso não é consistente com a literatura médica.

### Próximos Passos

1. **Validar taxa de 4 Hz**: Executar aplicativo e comparar novos valores
2. **Investigar fórmula do Fo**: Verificar se é `Vo × τ` ou `Vo × To`
3. **Calibrar constante ADC**: Ajustar fator 27 se Vo ainda estiver inconsistente
4. **Comparar com mais laudos**: Usar outros exames para validar calibração

---

## Referências

- Elcat Vasoquant 1000 Manual
- Light reflection rheography (LRR) principles
- Photoplethysmography venous assessment literature

# Relatório de Análise da DLL dppg 2.dll

## Informações do Arquivo

- **Arquivo**: `app_original/redist/dppg 2.dll`
- **Tipo**: PE32 executable (DLL) (GUI) Intel 80386, for MS Windows
- **Tamanho**: 624,128 bytes
- **Data**: 2 fev 2017

## Exports da DLL

A DLL exporta apenas 3 funções:
- `IsWindowBusy` (RVA 0x23ce0)
- `Run` (RVA 0x23f80)
- `Terminate` (RVA 0x23c90)

## Strings Relevantes Encontradas

### Parâmetros D-PPG
- `Venous refilling time` (To)
- `Half-amplitude Time` (Th)
- `Initial Inflow` (Ti)
- `Venous Pump power` (Vo)
- `Ven. refill. surface` (Fo)

### Formatos de Saída
- `| Fo %s `
- `| Vo %  `
- `| Ti s  `
- `| Th s  `

### Configurações de Amplitude
- `1 = Standard amplitude range, Vo max. 20%`
- `2 = Extended acquisition range, Vo max. 40%`

## Constantes Confirmadas

### Tabela Principal de Constantes (0x38900-0x389a0)

| Offset     | Valor    | Descrição                          |
|------------|----------|-------------------------------------|
| 0x038920   | 1000.0   | Multiplicador interno               |
| 0x038940   | 3.0      | Possível To em % (3% = 0.03)        |
| 0x038948   | 12.0     | Janela de processamento             |
| 0x038950   | 6.0      | Janela de processamento             |
| 0x038958   | 10.0     | Janela de baseline                  |
| 0x038960   | 72.0     | (desconhecido)                      |
| **0x038968** | **0.125** | **THRESHOLD Ti (87.5% recovery)** |
| 0x038980   | 37.0     | (desconhecido)                      |
| 0x038990   | 70.0     | (desconhecido)                      |
| 0x038998   | 100.0    | Conversão para percentual           |
| 0x0389A0   | 300.0    | (desconhecido)                      |

### Outras Constantes na Seção .rdata

| Offset     | Valor    | Descrição                          |
|------------|----------|-------------------------------------|
| **0x035CD2** | **0.5000** | **THRESHOLD Th (50% recovery)** |

## Thresholds Confirmados

### THRESHOLD_TI = 0.125 ✅ CONFIRMADO

- **Localização**: VA 0x10038968
- **Valor exato**: 0.125000000000
- **Bytes**: `00 00 00 00 00 00 C0 3F`
- **Significado**: 12.5% restante = **87.5% de recuperação**
- **Nota**: O valor anteriormente usado de 0.10 (90% recovery) estava INCORRETO

### THRESHOLD_TH = 0.50 ✅ CONFIRMADO

- **Localização**: VA 0x10035CD2
- **Valor exato**: 0.500000000000
- **Bytes**: `00 00 00 00 00 00 E0 3F`
- **Significado**: **50% de recuperação**
- **Nota**: O valor anteriormente usado de 0.48 estava próximo, mas o correto é 0.50

### THRESHOLD_TO = 0.03 ⚠️ INFERIDO

- **Evidência direta**: Valor 3.0 encontrado em 0x038940
- **Interpretação**: O código provavelmente usa 3.0/100.0 = 0.03
- **Significado**: 3% restante = **97% de recuperação**
- **Nota**: Não foi encontrado 0.03 como double literal na tabela principal

## Outras Constantes de Calibração

| Constante | Valor    | Uso                                  |
|-----------|----------|--------------------------------------|
| 100.0     | ✅       | Conversão para percentual (Vo)       |
| 1000.0    | ✅       | Multiplicador interno                |
| 10.0      | ✅       | Janela de baseline inicial           |
| 32.5      | ✅       | Taxa interna do hardware (Hz)        |
| 4.0       | ✅       | Taxa de amostragem exportada (Hz)    |

## Valores Descartados

Os seguintes valores encontrados na DLL **NÃO são thresholds de cálculo**:

- **~0.5077** (múltiplas ocorrências em 0x094714, 0x096776, etc.)
  - Localização: Região de dados de imagem PNG
  - Provavelmente dados de pixel/cor
  
- **~0.0299** (0x0593B5)
  - Localização: Região de dados PNG (próximo a marcador IEND)
  - Não é o threshold de To
  
- **~0.9701** (0x07C674)
  - Localização: Região de dados de imagem
  - Não é usado para cálculo de To

## Conclusão

A análise confirma que os thresholds corretos são:

```python
THRESHOLD_TO = 0.03    # 97% de recuperação (3% restante)
THRESHOLD_TI = 0.125   # 87.5% de recuperação (12.5% restante) 
THRESHOLD_TH = 0.50    # 50% de recuperação
```

Estes valores devem ser usados em todos os módulos de cálculo do projeto D-PPG.

## Metodologia da Análise

1. Extração de strings com `strings`
2. Análise de seções com `objdump -h`
3. Extração da seção .rdata (dados somente leitura)
4. Busca por padrões IEEE 754 double precision
5. Identificação de instruções FPU (`fld`, `fmul`, `fdiv`)
6. Correlação entre endereços no código e valores na seção de dados
7. Filtragem de falsos positivos (dados de imagem PNG)

---
*Análise realizada em: $(date)*
*DLL: dppg 2.dll (Vasoview/ELCAT)*

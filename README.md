# D-PPG Vasoquant 1000 Reader

Aplicativo para leitura de dados do aparelho de fotopletismografia digital (D-PPG) Elcat Vasoquant 1000.

## Requisitos

- Python 3.8+
- numpy
- tkinter (geralmente incluído no Python)

## Instalação

```bash
pip install numpy
```

## Como Executar

```bash
python main.py
```

Ou diretamente:

```bash
python -m src.ui
```

## Uso

1. Clique em **"Conectar"** para estabelecer conexão TCP com o conversor Serial-WiFi
2. Aguarde **"Printer Online"** aparecer no Vasoquant
3. No Vasoquant, selecione um exame e **exporte/imprima**
4. Os blocos de dados são capturados automaticamente
5. Clique em **"Salvar CSV"** ou **"Salvar JSON"** para exportar

## Configurações Padrão

| Parâmetro | Valor |
|-----------|-------|
| IP | 192.168.0.234 |
| Porta | 1100 |
| Taxa de amostragem | 4.0 Hz |

## Estrutura do Projeto

```
dppg/
├── main.py              # Ponto de entrada
├── src/
│   ├── __init__.py      # Exports do pacote
│   ├── config.py        # Constantes e configurações
│   ├── models.py        # PPGParameters, PPGBlock
│   ├── analysis.py      # Cálculo de parâmetros (To, Th, Ti, Vo, Fo)
│   ├── protocol.py      # Parser do protocolo Vasoquant
│   ├── exporters.py     # Exportação CSV/JSON
│   └── ui.py            # Interface gráfica (Tkinter)
├── CLAUDE.md            # Documentação técnica
├── PARAMETROS_CALCULO.md # Documentação das fórmulas
└── README.md            # Este arquivo
```

## Módulos

| Módulo | Responsabilidade |
|--------|------------------|
| `config.py` | Constantes de configuração, parâmetros de calibração, protocolo |
| `models.py` | Classes de dados: `PPGParameters`, `PPGBlock` |
| `analysis.py` | Algoritmos de cálculo de parâmetros usando fitting exponencial |
| `protocol.py` | Decodificação do protocolo serial do Vasoquant |
| `exporters.py` | Funções de exportação para CSV e JSON |
| `ui.py` | Aplicação GUI com Tkinter |

## Parâmetros Calculados

| Parâmetro | Descrição | Unidade |
|-----------|-----------|---------|
| To | Tempo de reenchimento venoso | segundos |
| Th | Tempo de meia amplitude | segundos |
| Ti | Tempo de influxo inicial | segundos |
| Vo | Potência da bomba venosa | % |
| Fo | Capacidade da bomba venosa | %·s |

## Hardware

- **Aparelho**: Elcat Vasoquant 1000 D-PPG
- **Conversor**: TGY Cyber WS1C (Serial → WiFi)
- **Protocolo**: Serial RS-232, 9600 baud, 8N1

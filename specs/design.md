# 2 · Diseño

## Arquitectura

```
                 sábado (GitHub Actions)                       lunes–viernes
┌──────────┐  ┌────────┐  ┌───────────┐  ┌──────────┐  ┌────────┐      ┌─────────┐
│ universe │→ │  data  │→ │ strategy  │→ │ executor │→ │ report │      │  guard  │
│ (listas) │  │ (velas │  │ fases,    │  │ órdenes  │  │ data   │      │ stops   │
└──────────┘  │ seman.)│  │ resist.,  │  │ en       │  │ .json  │      │ que     │
              └────────┘  │ señales   │  │ Alpaca   │  └───┬────┘      │ falten  │
                          └───────────┘  └────┬─────┘      │           └────┬────┘
                                              ▼            ▼                ▼
                                         state/*.json   docs/ (GitHub Pages)
```

| Módulo | Responsabilidad | Requisitos |
|---|---|---|
| `bot/universe.py` | Componentes S&P 500, Nasdaq 100, STOXX 600; caché | R-U1, R-U3 |
| `bot/data.py` | Descarga diaria (Yahoo) y agregación semanal | R-U2, R-U4 |
| `bot/indicators.py` | MM30, pendiente, MRS, ratio de volumen | R-F1 |
| `bot/stages.py` | Máquina de estados de las 4 fases | R-F2, R-F3 |
| `bot/resistance.py` | Pivotes, zonas de resistencia, mínimos de corrección | R-R1…R-R3 |
| `bot/strategy.py` | Entradas, tamaño, stops, reducciones y salidas (funciones puras) | R-E, R-S, R-D |
| `bot/broker.py` | Cliente REST de Alpaca y bróker simulado para tests | R-X3 |
| `bot/executor.py` | Traduce decisiones en órdenes; ciclo semanal y guardián | R-E7, R-S2, R-S5, R-D6, R-X |
| `bot/report.py` | Rentabilidad, alfa, `docs/data.json` | R-W |
| `docs/index.html` | Panel estático | R-W |

La estrategia es pura (entra un DataFrame, sale una decisión) y no conoce el bróker:
por eso se puede probar con series sintéticas y cambiar de bróker sin tocarla.

## Clasificación de fases (R-F2)

```
arriba = pendiente_MM30 > +0,5 %   y cierre > MM30   → Fase 2, última_tendencia = 2
abajo  = pendiente_MM30 < −0,5 %   y cierre < MM30   → Fase 4, última_tendencia = 4
resto                                               → Fase 3 si última_tendencia = 2
                                                      Fase 1 en otro caso
```

La pendiente es la variación de la MM30 en 4 semanas. La antigüedad de la tendencia
(R-F3) cuenta las semanas desde que `última_tendencia` cambió por última vez, de modo
que una semana suelta de transición no reinicia una Fase 2 madura.

## Resistencias y filtro de entrada (R-R, R-E)

1. Máximos pivote de ±3 semanas en 104 semanas, más el máximo reciente no confirmado.
2. Se ordenan por precio y se agrupan en zonas con tolerancia del 3 %. Nivel de la zona = su máximo.
3. Solo cuentan las zonas por encima del cierre.
4. **Zona de ruptura** = la más cercana. Es válida si tiene ≥ 2 toques o su último toque tiene ≥ 3 semanas.
5. **Resistencia superior** = la siguiente zona por encima. Si no hay, es subida libre.

```
entrada = zona × 1,005        límite = entrada × 1,03
stop    = min(mínimo de la base, MM30) × 0,99
R/R     = (resistencia superior − entrada) / (entrada − stop)   → se exige ≥ 2
```

## Gestión de la posición (R-S, R-D)

Orden de evaluación cada fin de semana:

1. Fase 4 → salida total.
2. Reducciones no aplicadas aún: Fase 3 (50 %), ruptura sin volumen (50 %), MRS < 0 dos semanas (25 %). Se aplica la mayor y se marcan todas las disparadas.
3. Stop candidato: Fase 2 → `min(último mínimo de corrección, MM30) × 0,99`; Fase 3 → `último mínimo × 0,99`. Nuevo stop = `max(stop actual, candidato)`, siempre por debajo del cierre.

## Órdenes en Alpaca

| Acción | Orden |
|---|---|
| Entrada | `buy stop_limit gtc`. Se intenta como `oto` con `stop_loss`; si Alpaca lo rechaza, entrada simple y el guardián pone el stop al ejecutarse |
| Stop | `sell stop gtc` por toda la posición |
| Subir stop / reducir | cancelar stop → (venta parcial `market day`) → nuevo stop por el resto |
| Salida Fase 4 | cancelar stop → `sell market day` (se ejecuta en la apertura del lunes) |

Las órdenes del bot llevan `client_order_id` con prefijo `wb-` (`wb-ent-`, `wb-stp-`, `wb-red-`, `wb-exit-`).
Símbolos: Yahoo usa `BRK-B`, Alpaca `BRK.B`; la conversión vive en `broker.py`.

## Estado persistente (`state/`)

- `positions.json` — por símbolo: stop vigente, fecha de entrada, reducciones aplicadas, motivo de entrada.
- `pending.json` — entradas pendientes con su stop previsto (lo usa el guardián).
- `equity.csv` — fecha, patrimonio, liquidez (una fila por día).
- `analysis.json` — resultado del último análisis semanal.

Se versionan en el propio repositorio: cada ejecución hace commit.

## Rentabilidad y alfa (R-W1, R-W2)

- Rentabilidad = patrimonio / patrimonio del primer registro − 1.
- Referencia: SPY con dividendos (cierre ajustado), en base 100 desde la misma fecha.
- Alfa simple = rentabilidad bot − rentabilidad SPY.
- Alfa de Jensen = (media r_bot − β · media r_spy) × 52 con rentabilidades semanales, β = cov/var; tipo libre de riesgo 0.

## Parámetros

Todos en `config.yaml`; ningún umbral está escrito en el código de la estrategia.

## Riesgos conocidos

- Un hueco de apertura puede ejecutar el stop por debajo de su nivel.
- Los datos de Yahoo no son oficiales; un valor sin datos se omite esa semana (R-X4).
- Entre la ejecución de una entrada y la pasada del guardián puede haber unas horas sin stop si Alpaca rechaza la orden OTO.
- GitHub Pages gratuito exige repositorio público: la web y el estado de la cuenta paper serán visibles.

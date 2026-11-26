# 1 · Requisitos

Bot de trading semanal basado en el Análisis de Fases de Stan Weinstein.
Formato EARS (CUANDO / SI … ENTONCES el sistema DEBE …). Cada requisito tiene un
identificador que se referencia desde `design.md`, `tasks.md` y los tests.

## Contexto y decisiones cerradas

| Decisión | Valor |
|---|---|
| Bróker | Alpaca, cuenta **paper** (API REST v2) |
| Universo | S&P 500 + Nasdaq 100 (operables) y STOXX 600 (solo señal, ver R-U3) |
| Marco temporal | Velas semanales; media de 30 semanas |
| Momento de decisión | Fin de semana, mercado cerrado |
| Ejecución y web | GitHub Actions + GitHub Pages |
| Sentido | Solo largos |

## R-U · Universo y datos

- **R-U1** El sistema DEBE construir el universo con los componentes del S&P 500 y del Nasdaq 100, con caché local por si la fuente falla.
- **R-U2** El sistema DEBE trabajar con velas semanales (cierre de viernes) obtenidas agregando datos diarios, y DEBE descartar la vela de la semana en curso si no está cerrada.
- **R-U3** Alpaca solo opera acciones de EE. UU. Para los valores del STOXX 600 el sistema DEBE calcular fase y señales y mostrarlas en la web como «señal sin ejecución», y NO DEBE enviar órdenes.
- **R-U4** SI un valor tiene menos de 60 semanas de histórico, ENTONCES el sistema DEBE ignorarlo.

## R-F · Clasificación de fases

- **R-F1** El sistema DEBE calcular para cada valor: MM30 semanal, su pendiente (variación a 4 semanas), la Fuerza Relativa de Mansfield (52 semanas) frente a su índice y el ratio de volumen frente a la media de las 4 semanas previas.
- **R-F2** El sistema DEBE etiquetar cada semana como:
  - **Fase 2** — cierre sobre la MM30 y MM30 ascendente.
  - **Fase 4** — cierre bajo la MM30 y MM30 descendente.
  - **Fase 3** — cualquier otro estado cuando la última tendencia definida fue la Fase 2 (media que se aplana o precio que la pierde).
  - **Fase 1** — cualquier otro estado cuando la última tendencia definida fue la Fase 4 (suelo).
- **R-F3** El sistema DEBE conocer cuántas semanas lleva vigente la tendencia actual (antigüedad de la Fase 2).

## R-R · Resistencias

- **R-R1** El sistema DEBE detectar máximos pivote (máximo de una ventana de ±3 semanas) en las últimas 104 semanas y agruparlos en zonas de resistencia cuando difieran menos de un 3 %.
- **R-R2** Una zona es un nivel de ruptura válido si tiene al menos 2 toques o su último toque tiene 3 semanas o más. El máximo reciente aún no confirmado como pivote NO lo es (no hay base formada).
- **R-R3** Las zonas por debajo del cierre actual se consideran superadas y NO cuentan.

## R-E · Entradas

El bot no se adelanta a la ruptura: compra cuando ya está confirmada y en su retroceso.

- **R-E1** El sistema solo DEBE proponer compras en valores en **Fase 2**, o saliendo de la base (cierre sobre la MM30 y MM30 sin caer), con MRS > 0 y precio no extendido más de un 25 % sobre la MM30.
- **R-E2** DEBE existir una **ruptura confirmada**: en las últimas 6 semanas un cierre semanal superó en un 0,5 % una zona de resistencia válida, con un volumen esa semana de al menos 2× la media de las 4 semanas previas. SI el precio volvió a cerrar más de un 3 % por debajo del nivel roto, la ruptura se considera fallida.
- **R-E3** Con una ruptura confirmada el sistema DEBE colocar hasta dos órdenes límite GTC, cada una por la mitad del tamaño:
  - **compra en confirmación** — solo el fin de semana de la ruptura y si el cierre no supera en más de un 7 % el nivel roto; límite un 1 % sobre el último cierre;
  - **compra en retroceso** — durante toda la ventana de 6 semanas; límite un 1 % sobre el nivel roto.
- **R-E4** El sistema NO DEBE colocar una orden SI:
  - a) existe una resistencia anterior por encima tal que (resistencia − entrada) / (entrada − stop) < 2;
  - b) el stop inicial queda a más de un 15 % de la entrada;
  - c) el S&P 500 está en Fase 4.
  SI el S&P 500 está en Fase 3, el riesgo por operación DEBE reducirse a la mitad.
- **R-E5** El tamaño total DEBE calcularse por riesgo: 1 % del patrimonio dividido por la distancia al stop, con un máximo del 10 % del patrimonio por posición, un máximo de 15 posiciones y sin apalancamiento.
- **R-E6** CUANDO haya más candidatos que huecos, el sistema DEBE priorizar por MRS descendente. A una posición ya abierta solo se le puede añadir la compra en retroceso, una vez, y nunca si ha dado señales de debilidad.
- **R-E7** Las órdenes de entrada no ejecutadas DEBEN cancelarse y recalcularse cada fin de semana.
- **R-E8** Toda ruptura que no acabe en orden DEBE quedar registrada con su motivo y mostrarse en la web.

## R-S · Stops

- **R-S1** El stop inicial DEBE situarse un 1 % por debajo del menor entre el mínimo de la base y la MM30.
- **R-S2** Toda posición abierta DEBE tener en el bróker una orden **sell stop GTC** por la totalidad de sus títulos.
- **R-S3** En Fase 2 el stop DEBE subirse a un 1 % por debajo del menor entre el último mínimo de corrección confirmado y la MM30. En Fase 3 DEBE ajustarse bajo el último mínimo de corrección aunque quede por encima de la MM30.
- **R-S4** El stop NUNCA DEBE bajarse.
- **R-S5** SI una entrada se ejecuta entre semana sin stop asociado, ENTONCES el guardián diario DEBE colocarlo ese mismo día al nivel decidido el fin de semana. El guardián no toma ninguna otra decisión.

## R-D · Reducciones y salidas por debilidad

- **R-D1** CUANDO una posición pase a **Fase 3**, el sistema DEBE vender el 50 %.
- **R-D2** CUANDO la MRS sea negativa dos semanas seguidas, el sistema DEBE vender el 25 %.
- **R-D3** (Retirado: el volumen se exige antes de comprar, R-E2.)
- **R-D4** Cada regla de reducción DEBE aplicarse una sola vez por posición; si coinciden varias se aplica la mayor.
- **R-D5** CUANDO una posición pase a **Fase 4**, el sistema DEBE vender la totalidad a mercado en la siguiente apertura.
- **R-D6** Tras una reducción, el stop DEBE recolocarse por los títulos restantes.

## R-X · Ejecución

- **R-X1** El ciclo semanal DEBE negarse a ejecutarse si el mercado está abierto.
- **R-X2** El sistema DEBE ofrecer un modo `--dry-run` que calcule y registre las decisiones sin enviar órdenes.
- **R-X3** Las claves de Alpaca DEBEN leerse de variables de entorno y nunca guardarse en el repositorio.
- **R-X4** Un error con un valor NO DEBE detener el ciclo del resto.

## R-W · Web

- **R-W1** La web DEBE mostrar la rentabilidad acumulada desde la puesta en marcha del bot, el patrimonio con la liquidez y, con al menos 90 días de datos, el CAGR (rentabilidad anualizada) junto al del S&P 500.
- **R-W2** La web DEBE mostrar el alfa frente al S&P 500: exceso de rentabilidad acumulada y, con al menos 8 semanas de datos, alfa de Jensen anualizada y beta.
- **R-W3** La web DEBE mostrar la curva de patrimonio del bot y la del S&P 500 en base 100 sobre un mismo eje.
- **R-W4** La web DEBE mostrar las órdenes colocadas (entradas pendientes y stops), con tipo, precios y motivo.
- **R-W5** La web DEBE mostrar las posiciones abiertas con su fase y stop, las decisiones de la semana, las órdenes descartadas con su motivo y las señales europeas.
- **R-W6** La web DEBE ser estática y regenerarse en cada ejecución.

## Fuera de alcance

Cortos, opciones, intradía, ejecución en Europa, optimización de parámetros y backtesting (se propone como siguiente iteración).

# Bot Weinstein

Bot de trading semanal basado en el Análisis de Fases de Stan Weinstein. Cada sábado,
con el mercado cerrado, analiza velas semanales, deja colocadas en Alpaca (cuenta paper)
las compras tras rupturas confirmadas por volumen y en su retroceso, sube los stops, reduce posiciones débiles y publica
un panel web con la rentabilidad, el alfa frente al S&P 500 y las órdenes vivas.

El proyecto sigue un flujo *spec-driven*: lee primero `specs/`.

| Documento | Contenido |
|---|---|
| `specs/requirements.md` | Qué debe hacer el bot (requisitos numerados) |
| `specs/design.md` | Cómo lo hace: reglas, fórmulas, órdenes, arquitectura |
| `specs/tasks.md` | Tareas, su verificación y lo que queda pendiente |

Para cambiar el comportamiento: edita el requisito, ajusta `config.yaml` o el código y
actualiza el test que lleva el identificador del requisito en su nombre.

## Puesta en marcha

1. **Alpaca**: crea una cuenta en alpaca.markets y genera las claves de *Paper Trading*.
2. **GitHub**: crea un repositorio y sube esta carpeta.
3. **Secretos**: en *Settings → Secrets and variables → Actions* añade
   `ALPACA_API_KEY` y `ALPACA_SECRET_KEY`.
4. **Web**: en *Settings → Pages* elige *Deploy from a branch*, rama `main`, carpeta `/docs`.
5. **Primera prueba**: en *Actions → Ciclo semanal Weinstein → Run workflow* marca
   «Solo simular». Revisa en el registro qué órdenes habría enviado.
6. Si te convence, ejecútalo sin simular (en fin de semana). A partir de ahí corre solo:
   sábados el ciclo semanal, de lunes a viernes el guardián de stops.

GitHub Pages gratuito exige repositorio público: la web y el estado de la cuenta paper
serán visibles para cualquiera con el enlace. Las claves no se guardan nunca en el repositorio.

## Uso en local

```
pip install -r requirements.txt
pytest -q                              # 38 tests con series sintéticas
python -m bot.run_weekly --dry-run     # sin claves simula una cuenta de 100.000 $
python -m tools.make_demo              # regenera los datos de ejemplo del panel
```

Para ver el panel en local: `python -m http.server -d docs` y abre http://localhost:8000.

## Limitaciones que conviene conocer

- **Europa**: Alpaca solo opera EE. UU. Los valores del STOXX 600 se analizan y aparecen en la
  web como señal, sin órdenes. `universe/stoxx600.csv` trae unos 85 valores grandes; amplíalo
  con tickers de Yahoo (`SAN.MC`, `SAP.DE`…).
- **Sin backtest**: las reglas están probadas con series sintéticas y contra un bróker simulado,
  no sobre histórico real ni contra la API real de Alpaca. Úsalo en paper una temporada antes de
  plantearte dinero real.
- **Datos de Yahoo**: no oficiales; si un valor falla una semana se omite.
- **Aportaciones y retiradas** de la cuenta distorsionan la rentabilidad calculada.

# Contexto del proyecto: E-commerce contra entrega RD y Radar de productos ganadores

Última actualización: 17 de septiembre de 2026

Este documento reúne el contexto de negocio, la estrategia y el estado técnico del proyecto. Sirve para
arrancar cualquier conversación con una IA (Claude, Claude Code, Manus) o para incorporar a alguien del equipo
sin repetir explicaciones. El detalle técnico del código vive en `CLAUDE.md`, dentro del repositorio `radar/`.

---

## 1. Qué estamos construyendo

Un negocio de e-commerce "de verdad" en República Dominicana. Tiene dos piezas:

1. **Tiendas de contra entrega (COD).** Se lanzan una por una. Cada tienda se trabaja con todo el foco y el presupuesto
   publicitario hasta que escala. Con sus ganancias se financia la siguiente.
2. **La máquina de productos ganadores (Radar).** Es un sistema que detecta, filtra y valida productos de forma continua.
   Es el activo principal: las tiendas son vitrinas y la máquina es lo que se replica en otros mercados.

Principio central: la IA no adivina ganadores. Reduce dónde buscar y acelera la producción, pero el que
declara ganador a un producto es el mercado, con dinero real en anuncios.

## 2. Participantes y recursos

- **Operador y arquitecto técnico:** perfil emprendedor e IT, radicado en RD. Trabaja con Python, React y
  FilamentPHP, prioriza APIs y microservicios, y da mucha importancia a una UI/UX profesional, minimalista y funcional.
- **Inversionista:** aporta el capital inicial. Los acuerdos todavía no están formalizados (ver sección 11).
- **Capital inicial:** alrededor de USD 3,000.
- **Equipo:** por ahora sin equipo. Se contratará con las ganancias (ver sección 8).

## 3. Metas

| Horizonte | Meta | Nota |
|---|---|---|
| 6-8 semanas | Primer producto ganador con ganancia estable | Con USD 3,000 el objetivo es encontrar y aprender, no escalar |
| Intermedia | USD 10,000 de ganancia semanal en RD | Meta realista para el mercado dominicano |
| Visión | USD 100,000 de ganancia semanal, y luego más | Requiere expandirse a otros mercados COD |

Aritmética de la visión: con un margen neto de contra entrega del 15-25% (después de publicidad y devoluciones),
USD 100,000 de ganancia semanal implica unos USD 500,000 en ventas por semana. Con un ticket promedio cercano a
RD$2,000, son del orden de 2,000 órdenes diarias, una porción enorme del mercado dominicano. Por eso RD es el
laboratorio y el primer escalón. La expansión planificada es a Colombia, México y otros mercados COD
(Centroamérica, Puerto Rico, mercado hispano en EE. UU.).

## 4. Realidad del mercado dominicano

- **Competencia de courier barato.** Las compras en el exterior de hasta USD 200 están exentas de impuestos
  aduanales (Decreto 402-05, vigente según fuentes de finales de 2025; confirmar si cambia). Temu, Shein y Amazon entran barato.
- **No se compite en precio con productos genéricos.** Se compite en:
  - velocidad de entrega (24-48 h)
  - pago contra entrega
  - confianza por WhatsApp
  - productos que se venden con demostración en video
- **La operación de contra entrega decide la ganancia.** Hay que confirmar pedidos por WhatsApp, tener mensajería
  confiable y mantener inventario local pequeño. Se miden pedidos entregados y cobrados, no ventas.
- **Liquidez.** La mensajería liquida días después de la entrega, así que siempre hay dinero en la calle y hace falta reserva de caja.

## 5. Estrategia y reglas de ejecución

### Presupuesto inicial (USD 3,000)

| Rubro | Monto | Uso |
|---|---|---|
| Pruebas de publicidad | 1,800 | 10-12 productos, unos USD 150 cada uno (3-4 días a USD 40-50 diarios) |
| Muestras e inventario mínimo | 500 | Grabar videos propios y cubrir primeros pedidos |
| Reserva de caja | 500 | Dinero retenido por la liquidación de la mensajería |
| Plataforma y herramientas | 200 | Dominio, tienda, WhatsApp Business; landings hechas en casa |

### Reglas para no quemar el dinero

1. No construir software caro antes del primer ganador. La excepción es el Radar MVP, que tiene costo operativo bajo.
2. Preferir proveedores locales con inventario en RD que despachen contra entrega, para no inmovilizar capital.
3. Reglas de apagado frías, definidas antes de gastar:
   - si una prueba gasta USD 80 sin ventas, se apaga
   - si el costo por pedido confirmado supera el 30% del precio de venta, se apaga
4. Creativos grabados con el celular o generados con IA (UGC). En contra entrega, el video manda más que la tienda.
5. Es normal que solo 1 de cada 8-10 productos funcione.
6. Arquitectura de negocio: un backend único (logística, confirmación, datos de clientes, motor de productos)
   con varias vitrinas de nicho encima. Así cada tienda nueva nace con la inteligencia de la anterior.

### Economía por pedido (fórmula de control)

```
ganancia por pedido entregado = precio de venta
                              - costo del producto
                              - envío
                              - costo publicitario por pedido entregado
                              - costo prorrateado de devoluciones y pedidos no cobrados
```

## 6. La máquina de productos ganadores

Analogía: una refinería. Los colectores traen crudo de varias fuentes, el procesamiento lo limpia y agrupa,
la IA lo clasifica y al final del tubo solo sale el top 3 del día.

### Flujo

1. **Radar (IA/datos).** Recolecta más de 50 candidatos: anuncios activos, tendencias y marketplaces.
2. **Filtro (IA).** Puntúa los candidatos y deja un top 3.
3. **Creativos (IA).** Genera guiones, hooks, copy de landing y videos UGC.
4. **Prueba real (mercado).** Unos USD 150 por producto en anuncios.
5. **Decisión (mercado).** Escalar o apagar según las reglas.
6. **Aprendizaje.** Cada resultado, gane o pierda, recalibra el filtro. Esa es la ventaja competitiva a largo plazo.

### Criterios de un buen producto COD para RD

- Margen de 3x o más sobre el costo.
- Efecto "wow" en video, o resuelve un problema claro.
- No disponible fácilmente en tiendas locales.
- Ligero y no frágil.
- Sin tallas (las tallas disparan devoluciones).
- Precio de impulso entre RD$1,500 y RD$3,500.
- Bajo riesgo de competir con Temu o Shein en precio.

### Señales de "ganador" que mide el Radar

| Señal | Peso | Qué significa |
|---|---|---|
| Longevidad | 35% | Un anuncio activo más de 14 días indica que alguien lo paga porque vende (30+ días = 10) |
| Copias | 25% | Varias tiendas vendiendo el mismo producto es validación de mercado (5+ tiendas = 10) |
| Intensidad | 20% | Volumen de anuncios activos y engagement |
| Viabilidad | 20% | Evaluación de Claude según los criterios, ajustada por el margen real si ya se cargó costo y precio |

Penalizaciones multiplicativas: tallas x0.6, frágil x0.8, pesado x0.85.

## 7. Fuentes de datos y APIs (estado a septiembre 2026)

| Fuente | Acceso | Nota clave |
|---|---|---|
| Meta Ad Library | Apify (scrapers administrados, pago por resultado, entre menos de USD 1 y unos USD 8 por 1,000 anuncios) | La API oficial NO devuelve anuncios comerciales fuera de la UE/UK. No sirve para RD, MX ni CO |
| TikTok Creative Center | Actores comunitarios en Apify | Cubre unos 33 mercados; RD probablemente no está. Usar MX y CO como señal adelantada |
| AliExpress | API de afiliados, gratuita | Búsqueda por imagen para hallar proveedor y costo. La consulta de productos populares requiere permisos extra |
| Google Trends | Pendiente de evaluar | Complemento para validar demanda de búsqueda |

Técnica de búsqueda en Meta: palabras clave típicas de contra entrega ("pago contra entrega", "envío gratis",
"paga al recibir"). Así aparecen directamente los dropshippers latinos. Países monitoreados: DO, MX y CO.

Regla de seguridad: nunca conectar scrapers con la cuenta personal de Facebook ni con sus cookies. Solo actores
que trabajen sin login. Un bloqueo afectaría la cuenta publicitaria, que es la que genera ventas.

## 8. Operación diaria

### Sin equipo (unas 2 horas al día)

1. **Mañana, 20 min.** Revisar las métricas de ayer y aplicar las reglas de apagado o escalado.
2. **Radar, 40 min.** Revisar el top del dashboard o sumar candidatos manuales.
3. **Filtro, 15 min.** Decidir qué pasa a prueba.
4. **Creativos, 30 min.** Videos del producto en prueba.
5. **Noche, 15 min.** Confirmar pedidos por WhatsApp.

Ritmo semanal:
- **Lunes:** elegir 2-3 productos.
- **Martes y miércoles:** creativos y landing.
- **Jueves:** lanzar anuncios.
- **Viernes a domingo:** leer datos y decidir.

### Con equipo (orden de contratación)

1. Confirmación y logística por WhatsApp.
2. Editor de creativos.
3. Media buyer.

El operador se queda como arquitecto de la máquina y dueño de los datos.

## 9. Estado técnico: Radar MVP

Entregado como `radar-productos-ganadores.zip`, listo para Claude Code. Probado en entorno limpio: pasa 8 pruebas y el pipeline completo corre.

- **Stack:** Python, FastAPI y SQLAlchemy (SQLite hoy, Postgres después), Apify, Claude Haiku 4.5 con visión, y un dashboard HTML.
- **Servicios:** cada uno se ejecuta por CLI y por API.
  - colector de Meta
  - colector de TikTok
  - normalizador con Claude (agrupa copias del mismo producto entre anunciantes)
  - scoring
  - alerta por Telegram con el top 3
- **Dashboard:** ranking con barra de señal, detalle por producto, cálculo de margen en vivo, estados
  (candidato, en prueba, ganador, descartado), notas y hooks copiables. Probado en escritorio, móvil y modo oscuro.
- **Control de costos:** `APIFY_MAX_CHARGE_USD` limita el gasto por ejecución de actor y `MAX_NORMALIZE_PER_RUN` limita las llamadas a Claude.
- **Costo operativo estimado:** Apify del orden de USD 30-60 al mes por unos 1,000 anuncios diarios; Claude centavos al día; VPS USD 5-10 al mes.
- **Comandos de Claude Code:** `/primera-sesion`, `/revisar-actor`, `/diagnosticar`.

### Pendiente inmediato

1. Colocar `APIFY_TOKEN` y `ANTHROPIC_API_KEY` en `.env`.
2. Validar el input schema real del actor de Meta (`python -m app.cli schema apify/facebook-ads-scraper`).
3. Primera colecta barata: solo DO y 20 anuncios. Verificar el mapeo de campos.
4. Ajustar `USD_TO_DOP` a la tasa real (valor inicial: 60).
5. Programar el cron diario del pipeline.

### Hoja de ruta técnica

1. Enriquecimiento automático con AliExpress (búsqueda por imagen: proveedor y costo).
2. Postgres y docker compose con un contenedor por servicio.
3. Recalibrar los pesos del score con los resultados reales de productos probados.
4. Análisis de comentarios de anuncios para medir intención de compra.
5. Dashboard administrativo en FilamentPHP si la operación lo requiere.

## 10. Decisiones tomadas

- Piloto en RD, con expansión posterior a Colombia, México y otros mercados COD.
- Una tienda a la vez, reinvirtiendo ganancias en la siguiente.
- El modelo es contra entrega, sin competir en precio con plataformas asiáticas.
- Automatizar la búsqueda de productos con un Radar propio en lugar de depender solo de herramientas espía de suscripción.
- Usar Apify en lugar de la API oficial de Meta, por la limitación de cobertura.
- MVP técnico en Python con dashboard propio.

## 11. Preguntas abiertas y riesgos

- **Acuerdo con el inversionista sin formalizar.** Falta definir porcentajes, quién opera, qué pasa si se pierde el
  capital y cómo se reinvierten las ganancias. Es prioritario antes de gastar.
- Falta elegir la plataforma de tienda y la mensajería o proveedor logístico COD en RD.
- Falta elegir el nicho de la primera tienda o decidir si será tienda general de prueba.
- Hay que confirmar si hay proveedores locales con inventario que despachen contra entrega.
- Hay que medir la tasa real de devoluciones y pedidos no cobrados en RD.
- Riesgo regulatorio: cambios en la exención de USD 200 alterarían la competencia de courier.
- Riesgo de dependencia: los actores comunitarios de Apify pueden cambiar sus campos o dejar de mantenerse.

## 12. Glosario

- **COD (contra entrega):** el cliente paga al recibir el producto.
- **Producto ganador:** producto con demanda validada que genera ganancia estable con publicidad pagada.
- **UGC:** contenido con apariencia de cliente real, como testimonios o demostraciones grabadas con celular.
- **Hook:** frase o imagen de los primeros segundos del video que detiene el scroll.
- **CPA:** costo por adquisición, lo que cuesta en publicidad conseguir un pedido.
- **Longevidad:** días que un anuncio lleva activo; es el indicador principal de que vende.
- **Actor (Apify):** scraper publicado en Apify que se ejecuta bajo demanda y cobra por resultado o uso.
- **Normalizar:** convertir anuncios distintos del mismo producto en un solo registro con nombre común.

## 13. Preferencias de trabajo

- Nunca usar emojis en ningún entregable.
- Explicaciones breves y precisas, salvo que se pida más detalle; las analogías ayudan a entender conceptos nuevos.
- Diagnosticar primero y hacer cambios puntuales, sin reescrituras completas.
- Diseño minimalista, moderno, profesional y sobre todo funcional.
- Backend orientado a APIs y comunicación entre microservicios.
- Entregables compatibles con Manus (.zip o .skill) cuando aplique.

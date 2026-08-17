# BORRADOR -- NO ENVIADO

**Estado al 2026-08-17: escrito, verificado, pendiente de envío por decisión propia.**
Nico prefiere resolver primero el trabajo de nuestro lado (#154-#160) antes de
afirmarle nada al cliente. Cuando se envíe, registrar la fecha acá y en
`.claude/CONTEXTO.md` -- ese bookkeeping ya falló una vez y se creyó enviado algo
que no lo estaba.

**Cubre 3 de las 4 preguntas pendientes**: #135 (definición de "sin stock"),
#144 (exponente de la extrapolación), #146 (alcance del seguimiento de rotación
por pedido).

**Deliberadamente NO incluye** el punto 2 de #126 (movimientos de fin de mes):
la afirmación de "+87 unidades fechadas día 28-31" no se sostiene -- los números
redondos aparecen parejo en todos los días del mes, y el cliente nunca mandó
detalle diario contra el cual verificarlo. Depende de #160. Rodrigo ya había
pedido "más detalles para verlo", así que mandarle algo que no aguante un
cuestionamiento sería peor que no mandar nada.

**Todos los números fueron verificados contra producción** (no contra la réplica
local) el 2026-08-17: 4.964/5.639 artículos con mínimo > 0; 596 meses rotulados
"sin stock" que vendieron 1.537 unidades en 343 artículos; la aritmética de
59/192/930 unidades y los multiplicadores x1,97 y x6,39.

**Pendiente de decidir antes de enviar**: si se hace primero la medición de #144
(qué exponente predijo mejor contra años de historia). Si se hace, la pregunta 2
cambia de "¿qué preferís?" a "los datos dicen esto, ¿coincidís?" y hay que
reescribir esa sección.

**Nota de formato**: las tablas están en Markdown. Si se manda por mail, hay que
convertirlas a texto corrido o HTML.

---

Hola Rodrigo, ¿cómo estás?

Te escribo con tres temas juntos para no mandarte mails sueltos. Son independientes entre sí, podés contestarlos en el orden que quieras.

---

## 1. Qué significa "sin stock" — te pido una definición

Encontramos algo que preferimos consultarte antes de tocar nada, porque es una decisión tuya y no nuestra.

Hoy, cuando la planilla cuenta los "días con stock" de un artículo en el mes, solo cuenta los días en que el stock estuvo **por encima del mínimo que vos configuraste** para ese artículo — no los días en que había mercadería. Si un artículo tiene mínimo 6 y ese día había 3 unidades, hoy lo contamos como día sin stock, aunque hubiera mercadería para vender.

Esto no es un detalle de borde: **4.964 de 5.639 artículos (88% del catálogo) tienen un mínimo mayor a cero configurado**, así que les aplica a casi todos.

La consecuencia concreta, medida sobre los datos de producción: hoy la planilla rotula **596 meses como "mes completo sin stock" en los que en realidad se vendió** — 1.537 unidades repartidas en 343 artículos distintos. Son meses donde había mercadería (por debajo de tu mínimo), se vendió, y la planilla igual dice "sin stock".

Además tiene un efecto que va más allá del texto: esos meses quedan afuera del cálculo de la rotación sugerida. Un artículo que vive rozando su mínimo tiene casi toda su historia invisible para el cálculo, mientras vos lo ves rotulado "sin stock" sabiendo que tenía y vendía.

**La pregunta:** ¿para vos "sin stock" significa que no había nada de mercadería físicamente, o que estaba por debajo del mínimo que configuraste?

Según lo que nos digas, el camino es distinto:
- **Si tu criterio es el mínimo** (o sea, está bien como cuenta hoy): corregimos los textos de la planilla para que digan exactamente eso, "días con stock por encima del mínimo". No mueve ningún número.
- **Si querés ver stock físico**: cambiamos el criterio de conteo. Esto sí mueve números en toda la planilla (rotaciones incluidas), así que lo mediríamos primero y te avisaríamos el impacto antes de aplicarlo.

---

## 2. El exponente de la extrapolación — algo que no te habíamos dicho

Sobre tu contrapropuesta a la fórmula, donde pedías `p = 0.5`: verificamos tus cuatro ejemplos y están todos correctos. Tu fórmula es efectivamente una generalización de la nuestra, y con `p = 1` da exactamente lo que implementamos.

Pero hay algo que corresponde decirte antes de que confirmes, porque nosotros mismos te vendimos el tope como argumento a favor del cambio:

**Con `p = 0.5` se pierde el tope.** Nuestra fórmula actual (`p = 1`) nunca estima más del doble de lo que realmente se vendió, pase lo que pase — el multiplicador tiende a 2 por construcción. Tu versión con `p = 0.5` no tiene techo: crece sin límite a medida que quedan menos días observados.

Te lo muestro con el caso real que ya vimos juntos, el artículo I02552 (vendió 30 unidades en 1 solo día de un mes de 31):

| Fórmula | Estimación |
|---|---|
| La vieja (sin ponderar) | 930 unidades |
| `p = 1` (la actual) | **59 unidades** |
| `p = 0.5` (la que pedís) | **192 unidades** |

Con 1 día observado de 31, el multiplicador de `p = 0.5` llega a ×6,39. El de `p = 1` se queda en ×1,97.

**La pregunta:** ¿seguís prefiriendo `p = 0.5` sabiendo esto, preferís que mantengamos `p = 1`, o querés que lo midamos antes de decidir?

Sobre esa tercera opción: tenemos años de historia, y se puede medir. Para un mes donde el artículo se agotó el día N, sabemos cuánto vendió después en meses con stock completo — eso da una referencia de cuál era la demanda real, y permite ver qué exponente la hubiera predicho mejor. Lo podemos hacer nosotros sin que te insuma tiempo, y te contestamos con números en vez de opiniones. Conecta con lo que vos mismo pediste: evaluar la efectividad contra la venta real.

Mientras tanto no cambiamos nada en producción: sigue `p = 1`, que es lo que te comunicamos.

---

## 3. La rotación elegida por pedido — necesito definir el alcance

Sobre lo que nos pediste: poder cargar la rotación elegida final de cada pedido, para después evaluar la efectividad contra la venta real y tener un monitor de quiebre.

Nos parece muy valioso, y por una razón concreta: al comparar tus planillas contra nuestras sugerencias vimos que de 491 artículos, **solo 13 quedaron con el valor que proponía tu sistema sin tocar**. O sea que la persona que arma el pedido está aplicando criterio propio en casi todos los casos — y hoy ese criterio se pierde cuando se cierra el Excel. Registrarlo y poder contrastarlo contra lo que efectivamente pasó es cerrar el círculo.

Para poder construirlo necesito que me definas algunas cosas, porque hoy no existen en el sistema y no queremos adivinar:

1. **¿Dónde y cómo cargarías la rotación elegida?** ¿Desde la web, subiendo el Excel de vuelta con la columna completada, otra forma que te resulte más cómoda?

2. **¿Qué identifica un "pedido"?** Hoy el sistema no tiene ese concepto. ¿Es una fecha, un grupo de artículos, un archivo puntual?

3. **¿Contra qué medimos si la elección acertó?** ¿Qué horizonte de venta futura miramos — el mes siguiente, tres meses — y qué significaría para vos que "acertó"?

4. **El monitor de quiebre**: ¿lo pensás como una alerta, una pantalla dentro del sistema, un aviso por mail? ¿Qué tendría que pasar para que se dispare?

5. **La prioridad**: dijiste "ahora o más adelante". ¿Lo encaramos ahora o lo dejamos para después de otras cosas?

Con esas respuestas armamos el plan de trabajo y te lo pasamos antes de empezar.

---

Quedo atento a lo que me digas. Cualquiera de los tres podés contestarlo por separado si te resulta más práctico.

Saludos,
Nicolás

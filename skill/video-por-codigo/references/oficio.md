# Oficio · lo que hace que un video por código se vea profesional

Lectura obligatoria para el agente que hace la escena, y lista de chequeo al mirar la hoja de
cuadros. No es un estilo: es cómo se hace bien cualquier estilo.

## Sincronía

- La animación de un dato arranca en el segundo en que la voz lo dice (`window.VOZ`), no antes ni
  «más o menos». Una cifra que aparece dos segundos antes de que la nombren se siente torpe.
- Los cambios de escena caen en el inicio de una frase o de una sección, no a mitad de palabra.
- Si hay música sin voz, los cortes caen en el pulso de la música.

## Ritmo y respiración

- Entre 10 y 25 cambios de plano por minuto para piezas de negocio; más arriba marea, más abajo
  se vuelve diapositiva.
- Lo que hay que recordar (la cifra, la promesa, el cierre) se queda quieto al menos 1 segundo;
  el cierre, 2–3 segundos.
- El movimiento acelera, se sostiene y frena en seco. Nada se mueve a velocidad pareja: lo lineal
  se ve a programa de presentaciones.
- Lo normal es que el primer render vaya demasiado rápido. Ante la duda, alargar las pausas.
- Temblores de cámara y destellos se guardan para los 2 o 3 momentos clave del video; usados
  más, dejan de pesar.

## Estructura

Recursos que sostienen una pieza. **Son opciones, no una lista para cumplir**: escoge los que le
sirvan a esta historia; usar todos a la vez es justo lo que hace que los videos se parezcan.

- **Un hilo visual** que abre, cruza y cierra la pieza (una forma, una línea, un número que
  crece). El final retoma la imagen del inicio, cambiada por lo que pasó en medio.
- **Una sola protagonista por escena.** Una palabra o una cifra ocupa la pantalla; todo lo demás
  va pequeño y en segundo plano.
- **Un medidor que avanza** (año, porcentaje, contador, barra) le dice al espectador dónde está
  y le da sensación de progreso.
- Cada escena deja algo resuelto o revelado. Si se puede quitar sin que se note, sobra.

## Texto y tipografía

- Máximo dos familias tipográficas, cada una con un papel (titular / apoyo).
- El texto se comporta como un objeto más de la escena: se escribe, se arma, choca o desplaza
  otras formas. No es un letrero puesto encima del video.
- Tamaños: en 1920×1080, nada de texto por debajo de 28 px; titulares de 120 px en adelante.
  En vertical, todo un 30 % más grande y lejos de los bordes de arriba y abajo (ahí la app pone
  sus botones).
- Subtítulos (si los hay): máximo 2 líneas, cortados por sentido, no a la mitad de una idea.

## Color y luz

- Pocos colores. Un acento que se usa poco y por eso se nota.
- Mejor una fuente de luz clara que resplandor por todos lados: el brillo repartido abarata la imagen.
- Para que se note que la historia pasó a otra parte sirve cambiar el fondo, la escala, el
  encuadre o el ritmo. Basta con uno; no hace falta cambiarlos todos.

## Cifras

- Una cifra se **enacta**: el contador sube hasta el valor, la barra crece hasta su altura, el
  círculo se llena. Nunca aparece quieta en una tabla.
- Comparaciones lado a lado con la misma escala; si no, mienten.
- Formato local: 1.250.000 y 12,5 % en español.

## Técnica

- Determinismo: todo sale de `t`. Para azar, usar el `aleatorio(semilla)` de la plantilla.
- Nitidez: dibujar a la resolución final; si algo sale desenfocado, buscar primero dónde se está
  ampliando una imagen pequeña.
- Las fuentes web se esperan antes de pintar (la plantilla ya lo hace con `document.fonts.ready`).
- Imágenes (logo, fotos del cliente): se cargan antes de empezar y se dibujan sin deformarse.

## Señales de «hecho por IA» (y qué hacer en su lugar)

| Señal | En su lugar |
|---|---|
| Punto de color delante de un rótulo (`● EN VIVO`) | El rótulo solo; si marca un estado, el color va en el texto |
| Nota metida en cajita con borde de color | Dato grande a la izquierda y la frase clave resaltada con el acento |
| Rejilla de 4 íconos con título y texto | Una sola idea por escena, contada con movimiento |
| Degradado morado-azul neón, partículas flotando, cerebros brillantes | El color de la marca o del tema, con un solo acento |
| Todo entra con fundido y desplazamiento de 20 px | Cada entrada con intención distinta, ligada a lo que dice la voz |
| El nombre de la marca escrito con una fuente | El logo real como imagen |

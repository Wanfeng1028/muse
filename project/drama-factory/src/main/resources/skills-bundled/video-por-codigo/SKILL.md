---
name: video-por-codigo
description: "«hazme un video de/sobre X», «convierte esta propuesta (informe, presentación) en video», «un reel con estas cifras», «video animado», «video explicativo con voz», «motion graphics», «un video para LinkedIn/Instagram». Video MP4 hecho 100 % por código, sin grabar nada: guion, voz IA opcional sincronizada palabra por palabra, escenas animadas, subtítulos y revisión de cuadros antes de entregar. Entrega dos versiones para elegir. NO edita grabaciones reales (cortar silencios, muletillas) ni hace avatares."
---

# Video por código

Autor: Jorge Torres · Licencia MIT

Un video que se construye por código: cada cuadro lo pinta una página HTML con una función
`render(t)`, y un script lo graba a MP4. Si hay voz, el audio se convierte en datos (cuándo se dice
cada palabra) y la animación se dispara con esa palabra. Nadie ajusta tiempos a mano.

## 0. Antes de empezar

1. Correr `python3 <skill>/scripts/revisar_entorno.py`, donde `<skill>` es la carpeta de esta
   skill (en Windows, `py` en vez de `python3`). Si falta algo,
   instalarlo tú mismo siguiendo lo que imprime; al usuario solo se le pide la API key si no está.
2. Preguntar **solo lo que falte**, máximo 3 cosas, en una sola pregunta:
   - de qué es y para quién (si trae material, eso ya lo responde);
   - formato: **horizontal 16:9** (presentación, YouTube, LinkedIn) o **vertical 9:16** (reel, historia);
   - duración aproximada (por defecto 45–75 s) y si lleva **voz** (por defecto sí).
3. Crear la carpeta de trabajo con nombre neutro: `video-AAAA-MM-DD/` en la carpeta actual.
   El nombre de la carpeta también influye en el modelo: nada de «video-del-cohete».

**Regla de contenido:** cifras, nombres, clientes y logos salen **solo** del material que dio el
usuario. Si un dato falta, se pregunta o se omite; nunca se inventa una cifra para que el video
«quede mejor». El logo va siempre como archivo de imagen real, nunca escrito con una fuente.

**Estilo:** neutral por defecto (el modelo lo decide según el tema). Si el usuario da una marca
(colores, tipografía, logo), esa manda.

## 1. Guion → `narracion.json`

Leer [references/voz.md](references/voz.md). Escribir el guion por secciones:

```json
{
  "voz": "ash",
  "instrucciones": "Locutor latinoamericano, cálido y seguro, ritmo ágil.",
  "secciones": [
    {"id": "s1", "texto": "..."},
    {"id": "s2", "texto": "..."}
  ]
}
```

Mostrarle el guion al usuario **antes** de generar la voz (cuesta poco, pero rehacer cansa).
Si el usuario trajo su guion, se respeta palabra por palabra.

## 2. Voz (opcional)

```bash
python3 <skill>/scripts/voz.py video-AAAA-MM-DD/narracion.json
```

Genera `voz.wav`, `voz.js` (tiempos por palabra para la escena) y `transcripcion.txt`.
**Leer la transcripción**: si una sigla o un nombre salió mal pronunciado, reescribirlo como se
dice («KPI» → «ka, pe, i»; «ROI» → «retorno») y regenerar con `--solo s3`.
En `voz.js` las palabras van como las escribió el reconocedor: los números salen en dígitos
(«cuarenta» → `40`, y «por ciento» a veces desaparece), así que en la escena se busca `palabra('40')`.
Si la voz dura más de lo pedido (±15 %), recortar el guion y regenerar.

Sin voz: el video se arma con texto en pantalla y, si el usuario la tiene, una música
(`--musica archivo.mp3` al renderizar). Música solo con derechos de uso.

## 3. Dos versiones en paralelo

Una sola instrucción da resultados distintos cada vez, así que se hacen **dos** y el usuario
elige.

- Cada versión en su carpeta (`video-AAAA-MM-DD/a/`, `.../b/`), las dos sobre el mismo `voz.js`.
- El encargo para cada una se escribe con [references/encargo.md](references/encargo.md),
  **reemplazando `<skill>` por la ruta absoluta de esta skill** (el agente que lo recibe no sabe
  dónde está) y pegando el bloque de comandos que trae.
- **Subagentes en paralelo solo si tu entorno te avisa cuando terminan y puedes esperarlos.**
  Si no, o si no estás seguro, haz las dos versiones tú mismo, una tras otra. En paralelo,
  cada render con `--workers 2` para no ahogar el computador.
- Quién mira: cada agente revisa y corrige su propia versión (paso 6). Antes de entregar, tú
  vuelves a mirar las dos hojas; si una tiene un error, se la devuelves a su agente con el
  error concreto, no la arreglas a ciegas.

## 4. Contrato de la escena (lo único fijo)

- `escena.html` define `window.DURACION` (segundos) y `window.render(t)`, que pinta el cuadro
  exacto del segundo `t`.
- **Determinista**: el mismo `t` da siempre la misma imagen. Prohibido `Math.random()` sin
  semilla, `Date`, `setTimeout`, transiciones y animaciones CSS: todo movimiento sale de `t`.
- Tamaño fijo: 1920×1080 (horizontal) o 1080×1920 (vertical).
- La voz llega como `window.VOZ` (de `voz.js`): duración, secciones y palabras con su segundo.
- Todo lo demás (Canvas, SVG, DOM, WebGL, tipografías, color, cómo cuenta la historia) es libre.

## 5. Render

```bash
python3 <skill>/scripts/render.py video-AAAA-MM-DD/a/escena.html \
  --audio video-AAAA-MM-DD/voz.wav [--musica musica.mp3] [--vertical]
```

Sale `escena.mp4` al lado del HTML. Para revisar un tramo sin renderizar todo:
`--desde 12 --hasta 16 --salida tramo.mp4` (con su voz, para comprobar la sincronía).

## 6. Ver con ojos (obligatorio, mínimo una ronda)

```bash
python3 <skill>/scripts/hoja.py video-AAAA-MM-DD/a/escena.mp4
```

Abrir la imagen `escena.hoja.jpg` que genera y **mirarla**: el log de render no dice si el video está bien.
Revisar:
- texto legible: nada por debajo de 28 px en 1920×1080 (40 px en vertical);
- texto completo: dentro de un margen de 80 px, nada cortado, tampoco en las transiciones
  (renderizar con `--desde/--hasta` el segundo de cada cambio de escena);
- la cifra que más importa del material se ve **grande** en algún momento, no como rótulo;
- ningún plano con media pantalla vacía sin intención;
- cifras y nombres iguales al material;
- ningún tramo quieto sin intención; ninguna escena que repita a la anterior;
- que cada animación llegue con su palabra (revisar 2–3 momentos con `--desde/--hasta`).

Corregir, volver a renderizar y volver a mirar. No se entrega lo que no se ha visto.

## 7. Entregar

Dar las rutas de los dos MP4 y de sus hojas, decir en una línea qué hace distinta a cada una y
preguntar cuál sigue. Los comentarios del usuario se aplican **a esa versión** con el mismo
enfoque; no se vuelve a empezar de cero.

## Límites

- No edita grabaciones (cortar silencios, muletillas, tomas): eso es otra herramienta.
- No hace avatares ni clona voces. La voz es de OpenAI y suena a IA. Para piezas muy
  importantes, el usuario graba su propia voz: `voz.py --solo-tiempos grabacion.wav` saca los
  tiempos por palabra (deja `voz.wav` y `voz.js` al lado) y se sigue igual desde el paso 3.
- Videos de más de ~3 minutos: posibles, pero conviene dividirlos en partes.

# Guion para voz

Un guion para leer no es un guion para oír. Lo que se escucha tiene que entenderse a la primera.

## Largo

- La voz IA en español habla a unas **120 palabras por minuto** (medido con `ash` y «ritmo
  ágil»): 45 s ≈ 90 palabras, 60 s ≈ 120. Más las pausas de medio segundo entre secciones.
- La duración que pidió el usuario manda, con ±15 %. Si `voz.py` da más, se recorta el guion
  (no se acelera la voz).
- Dividir en 4–8 secciones (`s1`, `s2`…). Cada sección es un cambio de idea; entre secciones el
  script deja un respiro de medio segundo.

## Cómo se escribe

- Frases cortas, de una idea. Si hay que tomar aire a mitad de una frase, se parte en dos.
- Lo importante al final de la frase («el costo bajó un 40 %», no «un 40 % bajó el costo»).
- Un gancho en la primera frase: una cifra, una pregunta o una tensión. Nada de «Hola, en este
  video vamos a ver…».
- Cierre con una sola acción o una sola idea para recordar.
- Cifras redondeadas para el oído: «casi un millón trescientos mil», no «1.287.413». La cifra
  exacta puede ir en pantalla.

## Pronunciación (la voz IA se equivoca aquí)

| Escrito | Escribir para la voz |
|---|---|
| Siglas que se deletrean: KPI, CRM, SEO | «ka, pe, i» · «ce, erre, eme» · «se, o» (o la palabra completa) |
| Siglas que se leen como palabra: ONU, OTAN | se dejan igual |
| Porcentajes y monedas: 12,5 % · US$ 3.000 | «doce coma cinco por ciento» · «tres mil dólares» |
| Nombres en inglés | como suenan: «Méta», «Gúgol» si la voz los dice mal |
| Fechas: 1/10/2026 | «primero de octubre» |

Después de generar, `transcripcion.txt` muestra lo que entendió un reconocedor de voz. Si una
palabra sale mal ahí, **escucha esa sección** (`secciones/sN.mp3`) o dile al usuario que la
escuche: a veces la voz la dijo bien y fue el reconocedor el que se equivocó. Si la voz sí la dijo
mal, se corrige el texto de esa sección y se regenera con `--solo sN`.

La grafía para la voz («lids», «ka, pe, i») vive **solo** en `narracion.json`. Lo que se escribe en
pantalla sale del material original («leads», «KPI»); al agente de la escena se le dice así.

En `voz.js` los números quedan en dígitos y «por ciento» puede desaparecer: «sesenta y dos por ciento»
puede quedar solo como la palabra `62`. En la escena se busca `palabra('62')`, nunca `'62%'`.

## Voces de OpenAI

`alloy`, `ash`, `ballad`, `coral`, `echo`, `fable`, `nova`, `onyx`, `sage`, `shimmer`, `verse`.
Para español latinoamericano funcionan bien `ash` y `onyx` (masculinas) y `coral` y `nova`
(femeninas). El campo `instrucciones` controla acento, tono y ritmo: «acento colombiano neutro,
tono seguro y cercano, ritmo ágil sin atropellarse».

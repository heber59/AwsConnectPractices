# Ampliacion local de tarjetas — AnyBankWelcome

Preparado el 11 de noviembre de 2026 para probar en un nuevo workspace. No publicado ni probado con llamadas.

## Archivos

- `acxd/AnyBankWelcome.flow.json`: version ampliada del recorrido existente. Conserva las ramas account, card y transfer y la rama VIP heredada. La rama card ahora aclara el caso antes de escalar.
- `acxd/cardRequestType.json`: definicion de la nueva variable de contexto.
- `acxd/handoffSummary.json`: variable existente reutilizada para un resumen fijo del motivo confirmado. No es un resumen generado de toda la conversacion.
- `acxd-exports/current/`: respaldo original conservado sin cambios.

## Recorrido

Bienvenida -> clasificacion principal -> card -> aclarar motivo -> confirmar -> guardar contexto -> Escalate -> Connect -> cola de tarjetas.

| Motivo | cardRequestType | Frase para probar |
| --- | --- | --- |
| Perdida o robo | lost_stolen | Me robaron la tarjeta y quiero bloquearla |
| Cargo no reconocido | unrecognized_charge | Aparece una compra que yo no hice |
| Bloqueo o rechazo | blocked_declined | Mi tarjeta rechaza las compras |
| Dano o reposicion | damaged_replacement | El chip esta danado y necesito otra tarjeta |
| Otra consulta | other | Quiero hablar con un asesor de tarjetas |
| Fallo o timeout | unknown | Simular timeout/failure en el nodo de tarjetas |

Todas las salidas escriben routingDepartment=card, cardRequestType y handoffSummary antes de escalar. Perdida/robo tiene precedencia sobre cargo no reconocido; este tiene precedencia sobre rechazo y dano. Si ocurren varios problemas, el resumen fijo solo identifica el motivo prioritario; el asesor debe revisar el resto de la conversacion.

El nodo no tiene herramientas conectadas. No consulta datos, autentica clientes, bloquea/desbloquea tarjetas, registra disputas ni solicita reposiciones. Nunca pide PIN, CVV, contrasenas, codigos de un solo uso ni numeros completos. Las preguntas generativas siguen el idioma del cliente; los mensajes fijos heredados y nuevos estan en ingles. Traducir/configurar el idioma antes de probar telefonia en espanol: la definicion heredada solo declara en-US.

## Configurar en el proximo workspace

1. Recrear las dependencias de la bienvenida original y las variables de contexto, incluidas routingDepartment, customerTier y handoffSummary. Crear cardRequestType usando la definicion adjunta.
2. Usar AnyBankWelcome.flow.json como definicion de trabajo para recrear/actualizar AnyBankWelcome mediante el mecanismo compatible del workspace. No es un paquete de importacion de UI verificado: deriva del respaldo SDK, y la creacion/publicacion requiere validacion en el workspace destino. No copiar saveId ni metadatos del workspace anterior.
3. Revisar el modelo generativo disponible y las configuraciones de idioma. La copia conserva el modelo del respaldo original.
4. La rama VIP heredada sigue enviando a tarjetas antes de esta nueva aclaracion; no valida membresia y no implementa prioridad. Revisarla antes de habilitarla en el destino.
5. Compilar y desplegar la aplicacion ACXD. Vincular el bloque Agentic CX de Connect al workspace, aplicacion y alias nuevos.
6. En la salida Escalation de Connect, copiar $.AgenticCX.ContextVariables.routingDepartment a $.Attributes.routingDepartment como en la practica actual. Mantener la comparacion exacta card -> cola de tarjetas del destino.
7. Copiar tambien $.AgenticCX.ContextVariables.cardRequestType y $.AgenticCX.ContextVariables.handoffSummary a atributos de contacto cardRequestType y handoffSummary. Configurar su visualizacion en el espacio del agente si se desea: definirlos no los muestra automaticamente.
8. Conectar las otras ramas a las colas de cuentas y transferencias del nuevo sandbox y publicar el flujo Connect. Los IDs y ARNs anteriores requieren remapeo.

## Pruebas pendientes en destino

- Probar cada frase de la tabla, confirmar el motivo y verificar los tres atributos y la llegada a la cola de tarjetas.
- Corregir una clasificacion: indicar primero rechazo y despues aclarar que la tarjeta fue robada; debe terminar en lost_stolen.
- Reportar robo y cargo no reconocido a la vez: lost_stolen tiene precedencia, sin afirmar que se bloqueo la tarjeta.
- Pedir directamente un humano: other, sin insistir en detalles.
- Dar una descripcion ambigua: debe aclarar y confirmar antes de elegir motivo.
- Simular timeout/failure: unknown y escalamiento a tarjetas.
- Pedir saldo y ayuda con una transferencia: deben conservar sus ramas originales, sin entrar en la aclaracion de tarjetas.
- Probar con agente disponible y no disponible. Esperar en cola no equivale a error.
- Verificar que no promete reembolso, bloqueo, desbloqueo, reposicion ni apertura de disputa.

Validacion local realizada: JSON legible, referencias de nodos existentes, correspondencia entre indices de salida y motivos, contexto de las seis salidas y conservacion de las ramas originales ajenas a tarjetas. No valida la clasificacion del modelo, el esquema del servicio ni la publicacion.

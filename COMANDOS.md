# Qué podés hacer con la flota

Chuleta para {{human.name}}. `flota` la muestra, con lo que está pendiente ahora;
`flota <tema>` muestra una sola sección (por ejemplo `flota clusters`). Los agentes
la tienen en `/home/agents/etc/COMANDOS.md` y te la muestran si preguntás.

"Decile a X" es una frase para el chat de esa sesión. Lo demás se corre en una
terminal tuya, salvo que diga `tclaude` o `tcodex`.

Palabras: un **usuario IA** es un usuario de Linux que corre sesiones (`[ai_users]` de
tu `fleet.toml`); acá se usan los del ejemplo, `claude`, `codex` y `pensadero`, y
`t<usuario IA>` es su alias. Una **sesión de rol** tiene un brief (coord, arquitecto,
aparejador, maestro); una **sesión de trabajo** no, y le reporta a coord. Una **tarea** es un
objetivo que coord le pasa a una sesión de trabajo.

## Sesiones

| quiero… | cómo |
| :--- | :--- |
| arrancar las flotas después de un reinicio o un corte | `flota arrancar`: abre todas. A cada usuario IA de trabajo (claude, codex) te pide la passphrase de los clusters (si uno no tiene llave todavía, lo avisa y sigue) y le reanuda su coord, que retoma su flota; al pensadero le reanuda el maestro, en claude, con "Retomá el pensadero": te lista qué agentes de línea se pueden retomar, y reabre los que le digas. Entrás a la primera; las otras te esperan en `tcodex` y `tpensadero`. Para una sola: `flota arrancar pensadero` (o `codex`, o varias) |
| entrar a los usuarios IA | `tclaude`, `tcodex`, `tpensadero` (sesiones de tmux, cada una en su cajón de recursos) |
| hablar con el pensadero | con su maestro: en `tpensadero`, `cd ~/maestro && claude -c -n maestro` (o `codex resume --last`), la que tenga tokens. La ventana de tmux se llama como la carpeta (`maestro`), con `-n` o sin él; con `-n <nombre>`, como ese nombre |
| que una línea o un documento (una clase) tenga su propio agente | pedíselo al maestro: te propone para qué, y con tu sí lo abre él en una ventana nueva de `tpensadero` (claude o codex) y te dice cuál. Si pregunta si confiar en la carpeta, contestás vos ahí. Después trabajás con ese agente en su ventana: el maestro no lo dirige; lo abre, lo reabre después de un corte, y lee su carpeta cuando quieras pensar las líneas en conjunto. A uno de codex, escribile `/rename <nombre>` en su ventana, así el maestro lo encuentra. Si a esa herramienta se le acaban los tokens, abrí la otra en la misma carpeta y pedile `relevo` |
| mover un trabajo de un usuario IA a otro (un repo, un grupo de repos o carpetas) | `flota mover codex:repo_clases pensadero` (o `claude`). Frena si se perdería algo: cambios sin commitear, ramas sin aceptar, un stash, cualquier proceso del usuario IA trabajando ahí (una sesión, su daemon, un shell abierto en esa carpeta), un repo sin `main`, o un destino que ya existe. Cada repo queda clonado en tu `~/agents` y se le entrega al destino con su historia; lo que no es repo va con rsync. El origen va a la papelera del usuario IA, `~/work/TRASH`, con un renglón en su `README.md`: cuándo, de dónde, a dónde y por qué |
| vaciar la papelera de un usuario IA | mirá `~<usuario IA>/work/TRASH/README.md` y borrá lo que quieras: `sudo -u <usuario IA> rm -rf ~<usuario IA>/work/TRASH/<carpeta>`. Nada se borra solo |
| empezar una línea nueva | decíselo al maestro: crea el repo `~/work/lineas/<línea>` con su `RESUMEN.md`. Si tenés material, pasáselo: `flota pasar ~/<carpeta> pensadero:lineas/<línea>` |
| aceptar lo que hizo una línea | en la ventana de su agente (o del maestro): "aceptá la rama". La mergea a `main` de su repo. Las líneas no hace falta clonarlas: `flota traer` solo mira los repos que clonaste vos |
| darle al pensadero un documento con historia (clases, un libro) | como a cualquiera: `flota entregar ~/agents/<repo o grupo> pensadero`, o `flota mover` si está en otro usuario IA. Le llega a `~/work/<repo>`; commitea en ramas `pensadero/*`, que traés con `flota traer` |
| se acabaron los tokens de una herramienta y quiero seguir con la otra | en la misma carpeta, abrí la otra (`codex` o `claude`) y decile "venís de claude, corré `relevo claude`" (o al revés): lee el final de la otra conversación. Hoy, solo el pensadero tiene las dos |
| arrancar el coordinador | en `tclaude`: `cd ~/coord && claude -n coord`; en `tcodex`: `cd ~/coord && codex` |
| arrancar una sesión de trabajo | `cd ~/work/<repo> && claude -n <nombre>` (o `codex`); sin `-n` puede quedar `<nombre>-02` y los mensajes a `<nombre>` no le llegan. codex no tiene `-n`: en su ventana, `/rename <nombre>`, el mismo que la ventana de tmux (el coord de codex lo hace solo con las que abre). Después, `codex resume <nombre>` la retoma |
| que una sesión tome reglas nuevas, sin perder la conversación | `/exit` y `claude --continue` (o `codex resume`); si después el nombre no es el de siempre, `/rename <nombre>` |
| empezar una conversación nueva (más barato en tokens) | pedile que deje lo pendiente en sus notas; `/exit` y `claude -n <nombre>` |
| saber qué sesiones están gordas (gastan más tokens por mensaje) | coord te avisa solo, en una línea al final de lo que te contesta (como mucho cada `remind_minutes`, 5 por defecto); la tabla completa: decile "sesiones gordas" |
| achicar una sesión gorda sin perder el hilo | en su ventana: `/compact`; los vigilantes siguen vivos. Si notás que pierde algo (ids de jobs, por ejemplo), poné un foco en `[context] compact_focus` de `fleet.toml` y `fleetcontext` te lo agrega |
| ver los nombres de las sesiones | decile a cualquier sesión de claude: "listá los agentes" |
| no reiniciar todavía | una sesión que espera un job o un build: al reiniciar mueren sus vigilantes; esperá a que termine |
| saber quién me espera | decile a coord: "¿quién me espera?" |
| ver qué está haciendo cada sesión | decile a coord: "estado de la flota" |
| ver de un vistazo todos los usuarios IA | `flota estado`: roles y clusters de cada uno, sus sesiones vivas (dónde, cuánto quietas; en claude, los tokens), sus carpetas y cuándo cambió cada una, y lo que espera en el buzón. Solo lee |
| comparar un proyecto mío con el de la flota | `flota estado .` (en `~/agents/<proyecto>`), o `flota estado pensadero:proyecto`: no cambia nada. Deduce la flota (un proyecto vive en una sola). De cada repo: cuántas ramas hay para traer y si tu `main` tiene commits que la flota no. Del resto, lo que está fuera de git en los dos lados: archivos solo tuyos, solo de la flota, o más nuevos de un lado, con su tamaño; marca los de más de 1 GB |
| moverme en tmux | `Shift-←/→` ventanas; `C-a B` la que tocó la campana; `C-a d` salir sin cerrar |

## Aprender

| quiero… | cómo |
| :--- | :--- |
| que la flota proponga mejoras a sus reglas | decile a coord: "procesar lo aprendido"; cuando avise, decile al arquitecto: "procesá lo aprendido" |
| ver las propuestas pendientes | `buzon listar --tipo propuesta --sin-respuesta` |
| ver todas las propuestas y su estado | `buzon listar --tipo propuesta`: al lado de cada una, `-> ACEPTADA`, `-> RECHAZADA` o `-> HECHA` |
| que una sesión lea algo del buzón | decile: "leé lo que te mandó X en el buzón": lo lee, lo evalúa (solo lectura) y te muestra qué llegó, qué encontró y qué haría; no actúa hasta que digas que sí |
| que el aparejador revise una rama del arquitecto | el arquitecto le deja el pedido solo y te avisa; en `tcodex`, `cd ~/aparejador && codex` (`/status` debe decir `Workspace`: el planner declara de confianza las carpetas de rol de codex; si dice `Read Only`, abrilo con `codex -s workspace-write`), y decile "revisá lo que te mandó el arquitecto". Te muestra lo que encontró y le contesta al arquitecto; después decile al arquitecto "leé la respuesta del aparejador" |
| que una sesión atienda su buzón sola | decile, en su ventana: "quedate atento". Espera su propio correo (`buzon esperar`) y trata lo que llega como si vos le hubieras dicho que lo lea. Entre el arquitecto y el aparejador, además, las comprobaciones que uno le pide al otro se hacen sin preguntarte. Dura hasta que se resuelve lo que esperaba (una respuesta, una revisión, un problema): después de cada mensaje vuelve a esperar, y cuando se resuelve te avisa. Sin tu aviso, ninguna sesión espera, y la espera muere sola tras 2 horas sin correo (`[buzon] atento_minutos`, 120). Para cortarlo antes: "dejá de esperar", o Esc. En codex la espera no sobrevive al turno, así que la sesión deja una marca (`buzon atento`) y cierra su turno; el despertador, que `flota arrancar` deja corriendo en segundo plano (`flota estado` dice si corre; su registro, `~codex/.local/state/buzon/despertador.log`), le encola "Tenés correo nuevo: buzon leer <id>" cuando llega algo. Si no corre, codex no se despierta solo: `flota arrancar codex`. Y si cerrás la ventana de una sesión de codex que está atenta, el despertador la sigue despertando, pero corre en el servidor de codex sin ventana donde la veas: terminala antes con "dejá de estar atento" |
| pasar algo de una sesión a otra | decile a la primera: "mandale esto a X por el buzón". Sin pedírselo, solo mandan propuestas al arquitecto, la respuesta a lo que les hiciste leer, y el arquitecto sus pedidos de revisión (regla 10) |

## Clusters

| quiero… | cómo |
| :--- | :--- |
| abrir el acceso de los agentes | en `tclaude` (o `tcodex`): `/usr/bin/ssh-agent -a ~/.ssh/agente.sock` (una vez por arranque) y `/usr/bin/ssh-add` (`flota arrancar` lo hace por vos) |
| cerrarlo | en `tclaude` (o `tcodex`): `ssh-add -D` |
| ver qué corre en los clusters y si está vigilado | en `tclaude`: `fleetwatch` |
| agregar un cluster o cambiar qué puede hacer un agente ahí | editar `flota-<vos>/fleet.toml` (`box`, `writable`, `slurm_in_box`, `skill`), commit, `flota instalar --go`, y `flota cluster <cluster>`: corre `add-cluster` para cada usuario IA con box ahí, te muestra el plan y pregunta antes de aplicar |
| compartir una carpeta de mi home entre agentes (un stack) | en `fleet.toml`: `writable` para quien la arma y `readable` para quien la usa, en `/home/<vos>/agents/compartido` (o una carpeta adentro); `flota instalar --go` y `flota cluster <cluster>` |
| que un agente lea una carpeta mía, al día (un drive sincronizado) | en `fleet.toml`: `[machine] readable = { claude = ["~/drive"] }`, `bindfs` instalado, y `flota instalar --go`. La ve en `~/drive` de solo lectura; tus archivos no cambian. Si arriba de la carpeta hay algo con credenciales (`.gd`, `rclone.conf`, `.ssh`…) no la monta: declará subcarpetas, o sacalo de ahí |
| que un agente escriba en una carpeta compartida de esta máquina (un stack en `/home/shared/agents`) | en `fleet.toml`: `[machine] writable = { claude = ["/home/shared/agents"] }` y `flota instalar --go`. La carpeta queda tuya, grupo `agents`, `2775`, sin ACL; a su padre le da `o+x` (se pasa, no se lista). Puede escribir todo el grupo `agents`; quién lo hace lo dice la lista. Quién más la lee lo decidís vos, con sus bits de otros |
| ocultar algo más en la caja | en el cluster: agregar la ruta a `~/agents/ocultar` |
| proteger una carpeta de borrados accidentales | en el cluster: `chmod -R a-w <carpeta>` (`chmod -R u+w` para volver) |
| arreglar el grupo de lo que instaló una sesión | lo hacés vos, a mano, cuando quieras compartirlo (los agentes no se ocupan del grupo): en el cluster, desde tu sesión, `chgrp -R <grupo> <árbol>` y `chmod g+s` en sus directorios; el skill del sitio dice cuál es el grupo (en CCAD, `skills/ccad`, lección 6) |

## Repos y ramas

| quiero… | cómo |
| :--- | :--- |
| traer el trabajo de los agentes | `flota traer` (o `flota traer ~/agents/<clon>`): trae sus ramas, te muestra commits y diff de cada una, la mergea si decís que sí; después ofrece entregarles tu `main`. No instala: si cambió `flota` o tu configuración, te lo dice (`flota actualizar`). A mano: `git fetch <usuario IA>`, `git diff main...<usuario IA>/<rama>`, `git merge --ff-only <usuario IA>/<rama>` |
| darle tu `main` a cada flota que no lo tiene | `flota entregar`, sin nada: recorre tus clones, te lista los que tienen commits que su flota no tiene (cada proyecto vive en una sola), y con un sí se los entrega. `flota entregar .` y `flota traer .`, solo el repo donde estás (también desde una subcarpeta). `flota traer <proyecto>` de uno que todavía no clonaste busca qué flota lo tiene y te ofrece clonarlo de forma segura |
| darle un repo a un agente, o actualizar su copia | `flota entregar <tu clon> <usuario IA>`. Para actualizar, alcanza con `flota entregar .` (o la ruta del clon): va a quien ya lo tiene, donde lo tiene. Si nombrás a otro usuario IA, te avisa que sería una copia aparte y pregunta |
| nombrar una carpeta de una flota | como `scp`: `claude:proyecto_a` es `~claude/work/proyecto_a` (una línea del pensadero: `pensadero:lineas/<línea>`); `claude:` o `claude`, todo su `~/work`. Si el destino ya es una carpeta con otro nombre, lo pasado va adentro; si se llama igual que el origen, se actualiza |
| pasar un proyecto (repos y carpetas fuera de git) entre vos y su flota | siempre los dos lados, y la flota sola quiere decir la misma carpeta allá: parado en `~/agents/<proyecto>`, `flota pasar . pensadero` (de acá a su copia) o `flota pasar pensadero .` (de su copia a acá). Vale también para una subcarpeta: `flota pasar proyectos pensadero` parado en `~/agents/clases_posgrado` va a `pensadero:clases_posgrado/proyectos` (y la crea allá si no está); lo que git sigue en el repo que la contiene no va, eso es `flota entregar` o `traer`. Un proyecto vive en una sola flota: a otra, `flota mover`. Te muestra la comparación (`flota estado`) y un resumen ("2 repos traídos, 127 archivos sueltos copiados, 3,4 GB"), y pregunta una vez. Los repos van por git: los que entregás, con su historia; los que traés, rama por rama con su diff; uno que no tenías, clonado de forma segura. Lo demás por rsync: nunca un archivo que siga git, nunca encima de uno más nuevo, sin borrar nada. Con `--borrar`, en una carpeta sin repos adentro (aunque esté dentro de un repo), además borra los archivos sueltos que solo tiene el destino: te los lista antes de preguntar |
| traer algo de un agente (no un repo) | `flota pasar pensadero:ideas ~/agents` (una carpeta o un archivo) |
| pasar algo de una flota a otra (sin repos; un proyecto con repos se reasigna con `flota mover`) | `flota pasar claude:proyecto_a pensadero` (le llega a `~/work/proyecto_a`), o `flota pasar claude:proyecto_a pensadero:lineas/linea_a` (adentro de la línea `linea_a`). Si sale del pensadero, te pregunta antes: es confidencial |
| darle a un agente una carpeta o un archivo (no un repo) | `flota pasar <ruta> <usuario IA>`: le llega a su `~/work`, sin historia. Un archivo conserva su nombre: el destino es una carpeta |
| darle algo a un agente en una ruta precisa | `flota pasar ~/ideas claude:proyecto/docs/` (con la barra final): queda en `~/work/proyecto/docs/ideas`, y crea las carpetas que falten. Sin la barra, `claude:proyecto/docs/notas` le pone ese nombre a la copia. Solo dentro de su `~/work` |
| darle varias cosas de una | `flota pasar ~/a ~/b/c.pdf claude:proyecto`: cada una adentro de `proyecto`, con su nombre. Una sola lista, una sola pregunta |
| copiar carpetas sueltas de un árbol al mismo árbol en el agente | `flota pasar --arbol ~/drive ~/drive/x/a ~/drive/y/b/c pensadero:drive`: quedan en `~/work/drive/x/a` y `~/work/drive/y/b/c`, el resto del árbol no se toca. Repetí el comando para actualizarlas |
| cómo funciona `flota pasar` | es `rsync` en un solo sentido: te muestra qué cambiaría, pregunta, y pasa solo lo que cambió. Repetí el mismo comando para actualizar la copia. No borra nada, salvo con `--borrar` (el destino queda igual al origen; la lista marca qué se borra). Nunca pasa un `.git`. Si vos y el agente tocaron el mismo archivo, gana el origen: miralo en la lista antes de decir que sí |
| darle a un agente varios repos relacionados, para una sola sesión | ponelos juntos en `~/agents/<grupo>/` y `flota entregar ~/agents/<grupo> <usuario IA>`: le llegan a `~/work/<grupo>/`; la sesión se arranca en `~/work/<grupo>` (`flota traer` también los encuentra) |
| que el arquitecto se ponga al día con tu `main` | `flota traer` te lo ofrece al final; o `flota entregar ~/agents/flota claude` (o `flota-{{human.user}}`) |
| que el arquitecto traiga los cambios del grupo a tu `flota` | `git -C ~/agents/flota fetch origin` y `flota entregar ~/agents/flota claude`: le llega también `origin/main`, como `{{human.user}}/origin/main`; decile "actualizá flota con el grupo" |
| clonar un repo que creó un agente | `flota clonar <usuario IA> <repo>`: te muestra los comandos y los corre si decís que sí. Si el repo todavía no tiene `main` (uno nuevo), arranca de la única rama del usuario IA, o de la que contiene a todas las demás (ramas apiladas); si divergen, elegí con `--rama <rama>` (`flota clonar claude grupo/repo --rama claude/tema`). Si la aceptás: `git switch -c main`. Tu rama no sigue a ningún remoto: la primera vez que publicás, `git push -u origin main` |

Nunca corras git como vos dentro del `~/work` de un usuario IA (`/home/claude/work`,
`/home/codex/work`), ni le hagas push, ni agregues `safe.directory`.

## Instalar cambios

| quiero… | cómo |
| :--- | :--- |
| actualizar la flota con lo que hizo el arquitecto | `flota actualizar`: trae solo las ramas de `flota` y de tu `flota-{{human.user}}` (cada una con su diff y tu sí, como `flota traer`) y después corre `flota instalar --go`, que te muestra qué cambia y vuelve a preguntar. Instala aunque no haya nada nuevo para traer, así sirve también para algo que trajiste antes. Al final te avisa si hay un codex más nuevo que el fijado o un Claude Code más nuevo que el instalado; no actualiza ninguno. Después, `flota reiniciar` |
| instalar lo que cambió (reglas, roles, skills, `fleet.toml`, la máquina, las herramientas) | `flota instalar` muestra qué cambia (los diffs primero); `flota instalar --go` lo aplica, después de preguntarte |
| saber si falta instalar algo | `flota` (lo cuenta al principio) |

## Software de los agentes

| quiero… | cómo |
| :--- | :--- |
| actualizar codex de los agentes | cambiá `[software] codex` en `flota-{{human.user}}/fleet.toml`, `flota instalar --go`, y `flota actualizar codex`: lo instala como cada agente, en esa versión fija, y comprueba que sigan cargando sus reglas |
| actualizar claude | con el gestor de paquetes con que lo instalaste (`docs/instalacion.md`, paso 0; en Arch, `sudo pacman -Syu`): es del sistema y no se actualiza solo; después reiniciá las sesiones y preguntales algo de sus reglas |

## Recursos y tokens

| quiero… | cómo |
| :--- | :--- |
| saber cuánto queda del plan de tokens | `/usage` en cualquier sesión de claude (por ahora `flota` no lo suma) |
| cuántos mensajes intercambió coord sin mí | en el chat de coord: `fleetlog since-human`; el tope está en `fleet.toml` (`report_after`) |

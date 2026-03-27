import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import asyncio

import config
from utils import load_json, save_json

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

DIAS_CHOICES = [
    app_commands.Choice(name="Lunes", value="lunes"),
    app_commands.Choice(name="Martes", value="martes"),
    app_commands.Choice(name="Miércoles", value="miercoles"),
    app_commands.Choice(name="Jueves", value="jueves"),
    app_commands.Choice(name="Viernes", value="viernes"),
    app_commands.Choice(name="Sábado", value="sabado"),
    app_commands.Choice(name="Domingo", value="domingo"),
]

# Guarda el ID del mensaje embed de cada día
HORARIO_EMBEDS = {}

# Guarda qué días ya han sido reclamados
# Ejemplo: { "lunes": {"user_id": 123, "hora": "17:00", "zona": "España"} }
HORARIO_ASIGNADO = {}


# ───── DATA ─────
puntos = load_json("data/puntos.json", {})
sanciones = load_json("data/sanciones.json", {})
inactividad = load_json("data/inactividad.json", {})
aislamientos = load_json("data/aislamientos.json", {})
examenes = load_json("data/examenes.json", {})
oposiciones_examenes = load_json("data/oposiciones_examenes.json", {})
oposiciones_notas = load_json("data/oposiciones_notas.json", {})
oposiciones_inscritos = load_json("data/oposiciones_inscritos.json", {})
import json, os

def load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ───── PERMISOS ─────
def staff():
    async def check(i):
        return config.ROL_STAFF in [r.id for r in i.user.roles]
    return app_commands.check(check)

def staff_superior():
    async def check(i):
        return config.ROL_STAFF_SUPERIOR in [r.id for r in i.user.roles]
    return app_commands.check(check)

# ───── READY ─────
@bot.event
async def on_ready():
    await bot.tree.sync()
    check_inactividad.start()
    check_aislamientos.start()
    print("🟢 Bot listo")

# ───── /INACTIVIDAD ─────
@bot.tree.command(name="inactividad")
@staff()
async def inactividad_cmd(interaction: discord.Interaction, inicio: str, fin: str, razon: str):
    # Mensaje al usuario
    await interaction.response.send_message(
        "📨 Tu solicitud ha sido enviada al equipo superior ⚒️",
        ephemeral=True
    )

    embed = discord.Embed(title="📌 Nueva Solicitud de Inactividad",
                          color=discord.Color.orange())
    embed.add_field(name="Usuario", value=interaction.user.mention, inline=False)
    embed.add_field(name="Fecha de comienzo", value=inicio, inline=False)
    embed.add_field(name="Fecha de finalización", value=fin, inline=False)
    embed.add_field(name="Razón", value=razon, inline=False)

    canal = bot.get_channel(config.CANAL_INACTIVIDAD_SOLICITUDES)

    class InactividadView(discord.ui.View):
        @discord.ui.button(label="✅ Aceptar", style=discord.ButtonStyle.green)
        async def aceptar(self, i: discord.Interaction, _):
            # Añadir rol de inactivo
            rol_inactivo = i.guild.get_role(config.ROL_INACTIVO)
            await interaction.user.add_roles(rol_inactivo)

            embed_res = discord.Embed(title="Solicitud de Inactividad Aceptada",
                                      color=discord.Color.green())
            embed_res.add_field(name="Usuario", value=interaction.user.mention)
            embed_res.add_field(name="Aceptada por", value=i.user.mention)
            await bot.get_channel(config.CANAL_INACTIVIDAD_RESULTADOS).send(embed=embed_res)
            self.stop()

        @discord.ui.button(label="❌ Rechazar", style=discord.ButtonStyle.red)
        async def rechazar(self, i: discord.Interaction, _):
            embed_res = discord.Embed(title="Solicitud de Inactividad Rechazada",
                                      color=discord.Color.red())
            embed_res.add_field(name="Usuario", value=interaction.user.mention)
            embed_res.add_field(name="Rechazada por", value=i.user.mention)
            await bot.get_channel(config.CANAL_INACTIVIDAD_RESULTADOS).send(embed=embed_res)
            self.stop()

    await canal.send(embed=embed, view=InactividadView())

# ───── CHECK INACTIVIDAD ─────
@tasks.loop(minutes=10)
async def check_inactividad():
    hoy = datetime.now()
    for uid, data in list(inactividad.items()):
        fin = datetime.strptime(data["fin"], "%Y-%m-%d")
        if hoy >= fin:
            guild = bot.guilds[0]
            user = guild.get_member(int(uid))
            if user:
                await user.remove_roles(guild.get_role(config.ROL_INACTIVO))
            inactividad.pop(uid)
            save_json("data/inactividad.json", inactividad)

# ───── /AISLAR ─────
@bot.tree.command()
@staff_superior()
async def aislar(i: discord.Interaction, usuario: discord.Member, razon: str, minutos: int):
    roles_previos = [r.id for r in usuario.roles if r.id != i.guild.id]
    aislamientos[str(usuario.id)] = {
        "roles": roles_previos,
        "fin": (datetime.now() + timedelta(minutes=minutos)).isoformat()
    }
    save_json("data/aislamientos.json", aislamientos)

    await usuario.edit(roles=[i.guild.get_role(config.ROL_AISLADO)])
    canal = bot.get_channel(config.CANAL_AISLAMIENTOS)
    await canal.send(f"🔒 {usuario.mention} aislado por {minutos} min | {razon}")
    await i.response.send_message("✅ Usuario aislado", ephemeral=True)

# ───── CHECK AISLAMIENTOS ─────
@tasks.loop(minutes=1)
async def check_aislamientos():
    now = datetime.now()
    for uid, data in list(aislamientos.items()):
        if now >= datetime.fromisoformat(data["fin"]):
            guild = bot.guilds[0]
            user = guild.get_member(int(uid))
            if user:
                roles = [guild.get_role(r) for r in data["roles"] if guild.get_role(r)]
                await user.edit(roles=roles)
            aislamientos.pop(uid)
            save_json("data/aislamientos.json", aislamientos)

@bot.tree.command()
@staff()
async def anunciar(
    i: discord.Interaction,
    mensaje: str,
    canal: discord.TextChannel,
    ping: bool = False
):
    embed = discord.Embed(
        description=mensaje,
        color=discord.Color.orange()
    )
    embed.set_footer(text=f"Staff: {i.user}")

    content = "@everyone" if ping else None
    await canal.send(content=content, embed=embed)
    await i.response.send_message("📢 Anuncio enviado", ephemeral=True)

@bot.tree.command(name="activity-check")
@staff_superior()
async def activity_check(
    i: discord.Interaction,
    canal: discord.TextChannel,
    role: discord.Role
):
    embed = discord.Embed(
        title="📋 ACTIVITY CHECK",
        description=(
            f"Se informa a @everyone que si no reaccionas a este mensaje "
            f"se te quitará el rol **{role.name}** por inactividad.\n\n"
            "Atentamente,\nBot de Hispania"
        ),
        color=discord.Color.blue()
    )

    msg = await canal.send("@everyone", embed=embed)
    await msg.add_reaction("✅")

    await i.response.send_message("⏳ Activity check iniciado (24h)", ephemeral=True)

    await asyncio.sleep(86400)  # 24 horas

    msg = await canal.fetch_message(msg.id)
    reacted_users = [u async for u in msg.reactions[0].users()]

    removidos = []
    for member in role.members:
        if member not in reacted_users:
            await member.remove_roles(role)
            removidos.append(member.mention)

    if removidos:
        log = bot.get_channel(config.CANAL_ACTIVITY_LOG)
        await log.send(
            f"❌ Roles retirados por inactividad:\n" + "\n".join(removidos)
        )

@bot.tree.command()
@staff_superior()
async def ascender(
    i: discord.Interaction,
    usuario: discord.Member,
    role: discord.Role,
    razon: str = "No especificada"
):
    embed = discord.Embed(
        title="📈 Ascenso",
        color=discord.Color.green()
    )
    embed.add_field(name="Usuario", value=usuario.mention)
    embed.add_field(name="Nuevo rol", value=role.mention)
    embed.add_field(name="Staff", value=i.user.mention)
    embed.add_field(name="Razón", value=razon)

    canal = bot.get_channel(config.CANAL_ANUNCIOS)
    await canal.send(embed=embed)

    if role.position < i.user.top_role.position:
        await usuario.add_roles(role)
    else:
        await i.response.send_message(
            "⚠️ No se pudo añadir el rol porque es superior al tuyo",
            ephemeral=True
        )
        return

    await i.response.send_message("✅ Ascenso realizado", ephemeral=True)

@bot.tree.command()
@staff_superior()
async def descender(
    i: discord.Interaction,
    usuario: discord.Member,
    role: discord.Role,
    razon: str
):
    embed = discord.Embed(
        title="📉 Descenso",
        color=discord.Color.red()
    )
    embed.add_field(name="Usuario", value=usuario.mention)
    embed.add_field(name="Rol retirado", value=role.mention)
    embed.add_field(name="Staff", value=i.user.mention)
    embed.add_field(name="Razón", value=razon)

    canal = bot.get_channel(config.CANAL_ANUNCIOS)
    await canal.send(embed=embed)

    if role.position < i.user.top_role.position:
        await usuario.remove_roles(role)
    else:
        await i.response.send_message(
            "⚠️ No se pudo quitar el rol porque es superior al tuyo",
            ephemeral=True
        )
        return

    await i.response.send_message("✅ Descenso realizado", ephemeral=True)

@bot.tree.command(name="examen-crear")
@staff_superior()
async def examen_crear(
    i: discord.Interaction,
    titulo: str,
    pregunta1: str,
    pregunta2: str,
    pregunta3: str,
    pregunta4: str,
    pregunta5: str,
    role: discord.Role
):
    exam_id = str(len(examenes) + 1)

    examenes[exam_id] = {
        "titulo": titulo,
        "preguntas": [
            pregunta1,
            pregunta2,
            pregunta3,
            pregunta4,
            pregunta5
        ],
        "rol": role.id
    }

    save_json("data/examenes.json", examenes)
    await i.response.send_message(
        f"✅ Examen **{titulo}** creado con ID `{exam_id}`",
        ephemeral=True
    )

@bot.tree.command(name="examen-publicar")
@staff()
async def examen_publicar(i: discord.Interaction, examen_id: str, canal: discord.TextChannel):
    if examen_id not in examenes:
        await i.response.send_message("❌ Examen no encontrado", ephemeral=True)
        return

    data = examenes[examen_id]

    embed = discord.Embed(
        title="📝 NUEVO EXAMEN",
        description=f"**{data['titulo']}**\n\nPulsa el botón para comenzar.",
        color=discord.Color.blue()
    )

    class StartView(discord.ui.View):
        @discord.ui.button(label="📝 Empezar Examen", style=discord.ButtonStyle.green)
        async def start(self, b: discord.Interaction, _):
            await enviar_modal_examen(b, examen_id)

    await canal.send(embed=embed, view=StartView())
    await i.response.send_message("✅ Examen publicado", ephemeral=True)

async def enviar_modal_examen(interaction, examen_id):
    examen = examenes[examen_id]

    class ExamenModal(discord.ui.Modal, title=examen["titulo"]):
        respuestas = []

        for idx, pregunta in enumerate(examen["preguntas"], start=1):
            respuestas.append(
                discord.ui.TextInput(
                    label=f"P{idx}",
                    placeholder=pregunta,
                    style=discord.TextStyle.long,
                    required=True
                )
            )

        async def on_submit(self, i: discord.Interaction):
            embed = discord.Embed(
                title="📥 Examen enviado",
                color=discord.Color.orange()
            )
            embed.add_field(name="Usuario", value=i.user.mention, inline=False)

            for idx, r in enumerate(self.respuestas):
                embed.add_field(
                    name=f"P{idx+1}",
                    value=r.value,
                    inline=False
                )

            embed.set_footer(text=f"Examen ID: {examen_id}")

            class ReviewView(discord.ui.View):
                @discord.ui.button(label="Aceptar", style=discord.ButtonStyle.green)
                async def aceptar(self, b, _):
                    rol = b.guild.get_role(examen["rol"])
                    if rol:
                        await i.user.add_roles(rol)

                    result = discord.Embed(
                        title="✅ Examen Aprobado",
                        color=discord.Color.green()
                    )
                    result.add_field(name="Usuario", value=i.user.mention)
                    result.add_field(name="Staff", value=b.user.mention)

                    canal = bot.get_channel(config.CANAL_EXAMEN_RESULTADOS)
                    await canal.send(content=i.user.mention, embed=result)
                    await b.response.send_message("Examen aprobado", ephemeral=True)

                @discord.ui.button(label="Rechazar", style=discord.ButtonStyle.red)
                async def rechazar(self, b, _):
                    result = discord.Embed(
                        title="❌ Examen Rechazado",
                        color=discord.Color.red()
                    )
                    result.add_field(name="Usuario", value=i.user.mention)
                    result.add_field(name="Staff", value=b.user.mention)

                    canal = bot.get_channel(config.CANAL_EXAMEN_RESULTADOS)
                    await canal.send(content=i.user.mention, embed=result)
                    await b.response.send_message("Examen rechazado", ephemeral=True)

            canal = bot.get_channel(config.CANAL_EXAMEN_REVISION)
            await canal.send(embed=embed, view=ReviewView())
            await i.response.send_message(
                "📨 Examen enviado correctamente",
                ephemeral=True
            )

    modal = ExamenModal()
    for r in modal.respuestas:
        modal.add_item(r)

    await interaction.response.send_modal(modal)

@bot.tree.command(name="trabajo")
@staff()
async def trabajo(
    interaction: discord.Interaction,
    tipo: str,
    descripcion: str
):
    embed = discord.Embed(
        title="📄 Nuevo Trabajo Enviado",
        color=discord.Color.blue()
    )
    embed.add_field(name="Usuario", value=interaction.user.mention, inline=False)
    embed.add_field(name="Tipo de trabajo", value=tipo, inline=False)
    embed.add_field(name="Descripción", value=descripcion, inline=False)

    class TrabajoView(discord.ui.View):
        @discord.ui.button(label="✅ Aceptar", style=discord.ButtonStyle.green)
        async def aceptar(self, i: discord.Interaction, _):
            uid = str(interaction.user.id)

            # sumar punto
            puntos[uid] = puntos.get(uid, 0) + 1
            save_json("data/puntos.json", puntos)

            canal = bot.get_channel(config.CANAL_TRABAJOS_ACEPTADOS)
            await canal.send(
                f"✅ Trabajo de {interaction.user.mention} **ACEPTADO**\n"
                f"➕ +1 punto"
            )

            await i.response.send_message(
                "Trabajo aceptado correctamente",
                ephemeral=True
            )
            self.stop()

        @discord.ui.button(label="❌ Rechazar", style=discord.ButtonStyle.red)
        async def rechazar(self, i: discord.Interaction, _):
            await i.response.send_message(
                "Trabajo rechazado",
                ephemeral=True
            )
            self.stop()

    canal = bot.get_channel(config.CANAL_TRABAJOS)
    await canal.send(embed=embed, view=TrabajoView())

    await interaction.response.send_message(
        "📨 Tu trabajo ha sido enviado al alto mando",
        ephemeral=True
    )

@bot.tree.command(name="server")
@staff()
async def server(interaction: discord.Interaction, opcion: str):
    canal = bot.get_channel(config.CANAL_SERVER_STATUS)

    if opcion.lower() == "abrir":
        embed = discord.Embed(title="SERVIDOR ABIERTO",
                              description="El servidor está abierto, únete usando el código 9e8-0cc o buscando Hispania Hospital.",
                              color=discord.Color.green())
        embed.set_footer(text=f"Servidor abierto por: {interaction.user}")
        await canal.send("@everyone", embed=embed)

    elif opcion.lower() == "cerrar":
        embed = discord.Embed(title="SERVIDOR CERRADO",
                              description="Gracias por unirte al servidor. Esperamos verte más días!",
                              color=discord.Color.red())
        embed.set_footer(text=f"Servidor cerrado por: {interaction.user}")
        await canal.send(embed=embed)

    elif opcion.lower() == "votar":
        embed = discord.Embed(title="CONFIRMAR ASISTENCIA",
                              description="Reacciona a este mensaje si quieres que se abra el servidor. Votar y no unirte puede causar una sanción.",
                              color=discord.Color.orange())
        embed.set_footer(text=f"Staff que abrió la votación: {interaction.user}")
        msg = await canal.send("@everyone", embed=embed)
        await msg.add_reaction("👍")
    else:
        await interaction.response.send_message("❌ Opción inválida: Abrir / Cerrar / Votar", ephemeral=True)
        return

    await interaction.response.send_message("✅ Comando ejecutado correctamente", ephemeral=True)

# ================= ESTADOS =================

@bot.tree.command(name="oposiciones-empezada")
async def empezada(interaction: discord.Interaction, usuario: discord.Member):
    canal = interaction.guild.get_channel(config.CANAL_ESTADO_ID)
    await canal.send(f"▶️ {usuario.mention} ha **EMPEZADO**.")
    await interaction.response.send_message("✅ Estado actualizado.", ephemeral=True)

@bot.tree.command(name="oposiciones-acabada")
async def acabada(interaction: discord.Interaction, usuario: discord.Member):
    canal = interaction.guild.get_channel(config.CANAL_ESTADO_ID)
    await canal.send(f"⏹️ {usuario.mention} ha **FINALIZADO**.")
    await interaction.response.send_message("✅ Estado actualizado.", ephemeral=True)

@bot.tree.command(name="puntos-añadir", description="Añadir puntos a un usuario")
@staff()
@app_commands.describe(
    usuario="Usuario al que se le sumarán puntos",
    cantidad="Cantidad de puntos a añadir"
)
async def puntos_anadir(interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
    if cantidad <= 0:
        await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)
        return

    uid = str(usuario.id)
    puntos[uid] = puntos.get(uid, 0) + cantidad
    save_json("data/puntos.json", puntos)

    await interaction.response.send_message(
        f"✅ Se han añadido {cantidad} puntos a {usuario.mention}. Total ahora: {puntos[uid]} puntos.",
        ephemeral=True
    )

@bot.tree.command(name="puntos-restar", description="Restar puntos a un usuario")
@staff()
@app_commands.describe(
    usuario="Usuario al que se le restarán puntos",
    cantidad="Cantidad de puntos a restar"
)
async def puntos_restar(interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
    if cantidad <= 0:
        await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)
        return

    uid = str(usuario.id)
    puntos[uid] = max(puntos.get(uid, 0) - cantidad, 0)
    save_json("data/puntos.json", puntos)

    await interaction.response.send_message(
        f"✅ Se han restado {cantidad} puntos a {usuario.mention}. Total ahora: {puntos[uid]} puntos.",
        ephemeral=True
    )

@bot.tree.command(name="puntos-resetear", description="Resetear todos los puntos de todos los usuarios")
@staff_superior()
async def puntos_resetear(interaction: discord.Interaction):
    global puntos
    puntos = {}
    save_json("data/puntos.json", puntos)

    await interaction.response.send_message(
        "✅ Todos los puntos han sido reseteados correctamente.",
        ephemeral=True
    )

@bot.tree.command(name="oposiciones-anuncio")
@app_commands.describe(
    convocadas_por="Convocadas por",
    fecha="Fecha de la oposición",
    hora="Hora de la oposición",
    zona_horaria="Zona horaria",
    firmado_por="Firmado por",
    canal="Canal donde enviar el anuncio"
)
async def oposiciones_anuncio(
    interaction: discord.Interaction,
    convocadas_por: str,
    fecha: str,
    hora: str,
    zona_horaria: str,
    firmado_por: str,
    canal: discord.TextChannel = None
):
    if not ROL_STAFF(interaction.user):
        return await interaction.response.send_message("❌ No tienes permisos.", ephemeral=True)

    if canal is None:
        canal = interaction.channel

    embed = discord.Embed(
        title="📄 Nuevas oposiciones convocadas",
        description=(
            f"El staff **{convocadas_por}** ha convocado nuevas oposiciones.\n\n"
            f"📅 **Fecha:** {fecha}\n"
            f"⏰ **Hora:** {hora}\n"
            f"🌍 **Zona horaria:** {zona_horaria}\n\n"
            "Reacciona a este mensaje si puedes asistir.\n\n"
            f"**Atentamente:**\n{firmado_por}"
        ),
        color=discord.Color.gold()
    )

    msg = await canal.send(embed=embed)
    await msg.add_reaction("✅")

    await interaction.response.send_message(f"✅ Anuncio de oposiciones enviado en {canal.mention}", ephemeral=True)

@bot.tree.command(name="warn", description="Advertencia verbal")
@app_commands.describe(
    usuario="Usuario advertido",
    razon="Motivo de la advertencia"
)
async def warn(
    interaction: discord.Interaction,
    usuario: discord.Member,
    razon: str
):
    descripcion = (
        f"{usuario.mention}\n\n"
        "⚠️ **Advertencia Verbal Oficial**\n\n"
        "Este mensaje constituye una advertencia formal por parte del equipo de "
        "moderación del **Hispania Hospital**. No implica una sanción directa, pero "
        "sí deja constancia de una conducta inapropiada.\n\n"
        f"📝 **Motivo:**\n{razon}\n\n"
        "ℹ️ Se recomienda corregir esta conducta. La reiteración puede dar lugar "
        "a sanciones disciplinarias."
    )

    embed = discord.Embed(
        title="⚠️ ADVERTENCIA VERBAL",
        description=descripcion,
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Staff responsable: {interaction.user}")

    canal = bot.get_channel(config.CANAL_SANCIONES)
    await canal.send(usuario.mention)
    await canal.send(embed=embed)

    await interaction.response.send_message(
        "⚠️ Advertencia enviada correctamente.",
        ephemeral=True
    )

import discord
from discord import app_commands

@bot.tree.command(name="sancionar", description="Sanciona a un usuario")
@app_commands.describe(
    usuario="Usuario a sancionar",
    razon="Razón de la sanción",
    apelable="¿La sanción es apelable?"
)
async def sancionar(
    interaction: discord.Interaction,
    usuario: discord.Member,
    razon: str,
    apelable: bool
):
    await interaction.response.defer()

    guild = interaction.guild

    rol_1 = discord.utils.get(guild.roles, name="Sanciones: 1")
    rol_2 = discord.utils.get(guild.roles, name="Sanciones: 2")
    rol_3 = discord.utils.get(guild.roles, name="Sanciones: 3")

    if not rol_1 or not rol_2 or not rol_3:
        await interaction.followup.send(
            "❌ Faltan roles de sanciones (Sanciones: 1, 2 o 3).",
            ephemeral=True
        )
        return

    # Determinar sanción actual
    if rol_3 in usuario.roles:
        nivel = 3
    elif rol_2 in usuario.roles:
        nivel = 2
    elif rol_1 in usuario.roles:
        nivel = 1
    else:
        nivel = 0

    # Subir nivel
    if nivel == 0:
        await usuario.add_roles(rol_1)
        nuevo_nivel = 1
    elif nivel == 1:
        await usuario.remove_roles(rol_1)
        await usuario.add_roles(rol_2)
        nuevo_nivel = 2
    elif nivel == 2:
        await usuario.remove_roles(rol_2)
        await usuario.add_roles(rol_3)
        nuevo_nivel = 3
    else:
        nuevo_nivel = 3

    # Texto apelable
    texto_apelable = (
        "📨 **Esta sanción puede ser apelada** siguiendo los canales oficiales."
        if apelable
        else "🚫 **Esta sanción NO es apelable**."
    )

    # Embed principal
    embed = discord.Embed(
        title="🚨 SANCIÓN DISCIPLINARIA",
        description=(
            f"El usuario {usuario.mention} ha sido sancionado por el equipo de moderación.\n\n"
            f"**Razón:**\n{razon}\n\n"
            f"{texto_apelable}\n\n"
            f"**Nivel actual de sanciones:** {nuevo_nivel}/3"
        ),
        color=discord.Color.red()
    )

    embed.set_footer(text=f"Staff responsable: {interaction.user}")

    await interaction.followup.send(embed=embed)

    # Aviso especial al llegar a 3 sanciones
    if nuevo_nivel == 3:
        aviso = discord.Embed(
            title="⚠️ AVISO IMPORTANTE",
            description=(
                f"El usuario {usuario.mention} ha alcanzado **3 sanciones**.\n\n"
                "**Debe ser puesto en aislamiento con el comando /aislar de forma inmediata** según la normativa. --> Cualquier Staff puede hacerlo."
            ),
            color=discord.Color.dark_red()
        )
        await interaction.followup.send(embed=aviso)

@bot.tree.command(name="warn-staff", description="Advertencia verbal a un staff")
@app_commands.describe(
    usuario="Usuario advertido",
    razon="Motivo de la advertencia"
)
async def warn(
    interaction: discord.Interaction,
    usuario: discord.Member,
    razon: str
):
    descripcion = (
        f"{usuario.mention}\n\n"
        "⚠️ **Advertencia Verbal Oficial**\n\n"
        "Este mensaje constituye una advertencia formal por parte del equipo de "
        "moderación del **Hispania Hospital**. No implica una sanción directa, pero "
        "sí deja constancia de una conducta inapropiada.\n\n"
        f"📝 **Motivo:**\n{razon}\n\n"
        "ℹ️ Se recomienda corregir esta conducta. La reiteración puede dar lugar "
        "a sanciones disciplinarias."
    )

    embed = discord.Embed(
        title="⚠️ ADVERTENCIA VERBAL",
        description=descripcion,
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Staff responsable: {interaction.user}")

    canal = bot.get_channel(config.CANAL_SANCIONES_STAFF)
    await canal.send(usuario.mention)
    await canal.send(embed=embed)

    await interaction.response.send_message(
        "⚠️ Advertencia enviada correctamente.",
        ephemeral=True
    )

@bot.tree.command(name="sancionar-staff", description="Sanciona a un miembro del staff")
@app_commands.describe(
    usuario="Usuario a sancionar",
    razon="Razón de la sanción",
    apelable="¿La sanción es apelable?"
)
async def sancionar(
    interaction: discord.Interaction,
    usuario: discord.Member,
    razon: str,
    apelable: bool
):
    await interaction.response.defer()

    guild = interaction.guild

    rol_1 = discord.utils.get(guild.roles, name="Sanciones: 1")
    rol_2 = discord.utils.get(guild.roles, name="Sanciones: 2")
    rol_3 = discord.utils.get(guild.roles, name="Sanciones: 3")

    if not rol_1 or not rol_2 or not rol_3:
        await interaction.followup.send(
            "❌ Faltan roles de sanciones (Sanciones: 1, 2 o 3).",
            ephemeral=True
        )
        return

    # Determinar sanción actual
    if rol_3 in usuario.roles:
        nivel = 3
    elif rol_2 in usuario.roles:
        nivel = 2
    elif rol_1 in usuario.roles:
        nivel = 1
    else:
        nivel = 0

    # Subir nivel
    if nivel == 0:
        await usuario.add_roles(rol_1)
        nuevo_nivel = 1
    elif nivel == 1:
        await usuario.remove_roles(rol_1)
        await usuario.add_roles(rol_2)
        nuevo_nivel = 2
    elif nivel == 2:
        await usuario.remove_roles(rol_2)
        await usuario.add_roles(rol_3)
        nuevo_nivel = 3
    else:
        nuevo_nivel = 3

    # Texto apelable
    texto_apelable = (
        "📨 **Esta sanción puede ser apelada** siguiendo los canales oficiales."
        if apelable
        else "🚫 **Esta sanción NO es apelable**."
    )

    # Embed principal
    embed = discord.Embed(
        title="🚨 SANCIÓN DISCIPLINARIA",
        description=(
            f"El usuario {usuario.mention} ha sido sancionado por el equipo de moderación.\n\n"
            f"**Razón:**\n{razon}\n\n"
            f"{texto_apelable}\n\n"
            f"**Nivel actual de sanciones:** {nuevo_nivel}/3"
        ),
        color=discord.Color.red()
    )

    embed.set_footer(text=f"Staff responsable: {interaction.user}")

    await interaction.followup.send(embed=embed)

    # Aviso especial al llegar a 3 sanciones
    if nuevo_nivel == 3:
        aviso = discord.Embed(
            title="⚠️ AVISO IMPORTANTE",
            description=(
                f"El usuario {usuario.mention} ha alcanzado **3 sanciones**.\n\n"
                "**Debe ser puesto en aislamiento con el comando /aislar de forma inmediata** según la normativa. --> Cualquier Staff puede hacerlo."
            ),
            color=discord.Color.dark_red()
        )
        await interaction.followup.send(embed=aviso)

def is_staff_superior():
    async def predicate(interaction: discord.Interaction):
        rol = interaction.guild.get_role(config.ROL_STAFF_SUPERIOR)
        return rol in interaction.user.roles
    return app_commands.check(predicate)

@bot.tree.command(name="role-add", description="Añadir un rol a un usuario")
@is_staff_superior()
@app_commands.describe(
    usuario="Usuario al que se le añadirá el rol",
    rol="Rol que se añadirá"
)
async def role_add(
    interaction: discord.Interaction,
    usuario: discord.Member,
    rol: discord.Role
):
    await interaction.response.defer(ephemeral=True)

    try:
        await usuario.add_roles(rol, reason=f"Role-add por {interaction.user}")

        embed = discord.Embed(
            title="✅ Rol añadido",
            description=f"El rol **{rol.mention}** ha sido añadido a **{usuario.mention}**.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Staff: {interaction.user}")

        await interaction.followup.send(embed=embed)

    except discord.Forbidden:
        await interaction.followup.send(
            "❌ No tengo permisos para añadir ese rol (puede ser más alto que el mío).",
            ephemeral=True
        )

@bot.tree.command(name="role-remove", description="Quitar un rol a un usuario")
@is_staff_superior()
@app_commands.describe(
    usuario="Usuario al que se le quitará el rol",
    rol="Rol que se quitará"
)
async def role_remove(
    interaction: discord.Interaction,
    usuario: discord.Member,
    rol: discord.Role
):
    await interaction.response.defer(ephemeral=True)

    try:
        await usuario.remove_roles(rol, reason=f"Role-remove por {interaction.user}")

        embed = discord.Embed(
            title="❌ Rol quitado",
            description=f"El rol **{rol.mention}** ha sido quitado a **{usuario.mention}**.",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Staff: {interaction.user}")

        await interaction.followup.send(embed=embed)

    except discord.Forbidden:
        await interaction.followup.send(
            "❌ No tengo permisos para quitar ese rol (puede ser más alto que el mío).",
            ephemeral=True
        )

    
class SolicitudRolView(discord.ui.View):
    def __init__(self, usuario, rol):
        super().__init__(timeout=None)
        self.usuario = usuario
        self.rol = rol

    @discord.ui.button(label="Aceptar", style=discord.ButtonStyle.success)
    async def aceptar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.usuario.add_roles(self.rol)
        await interaction.response.send_message("✅ Rol concedido.", ephemeral=True)

    @discord.ui.button(label="Rechazar", style=discord.ButtonStyle.danger)
    async def rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Solicitud rechazada.", ephemeral=True)


@bot.tree.command(name="solicitud-rol")
async def solicitud_rol(interaction: discord.Interaction, rol: discord.Role, razon: str):
    canal = bot.get_channel(config.CANAL_SOLICITUDES_ROL)

    embed = discord.Embed(
        title="📥 Solicitud de Rol",
        description=(
            f"👤 Usuario: {interaction.user.mention}\n"
            f"🎭 Rol solicitado: {rol.mention}\n"
            f"📝 Razón: {razon}"
        ),
        color=discord.Color.orange()
    )

    await canal.send(embed=embed, view=SolicitudRolView(interaction.user, rol))
    await interaction.response.send_message("📨 Solicitud enviada.", ephemeral=True)

class TrasladoView(discord.ui.View):
    def __init__(self, usuario, rol_actual, rol_nuevo):
        super().__init__(timeout=None)
        self.usuario = usuario
        self.rol_actual = rol_actual
        self.rol_nuevo = rol_nuevo

    @discord.ui.button(label="Aceptar", style=discord.ButtonStyle.success)
    async def aceptar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.usuario.remove_roles(self.rol_actual)
        await self.usuario.add_roles(self.rol_nuevo)
        await interaction.response.send_message("✅ Traslado realizado.", ephemeral=True)

    @discord.ui.button(label="Rechazar", style=discord.ButtonStyle.danger)
    async def rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Traslado rechazado.", ephemeral=True)


@bot.tree.command(name="traslado")
async def traslado(
    interaction: discord.Interaction,
    rol_actual: discord.Role,
    rol_nuevo: discord.Role,
    razon: str
):
    canal = bot.get_channel(config.CANAL_TRASLADOS)

    embed = discord.Embed(
        title="🔄 Solicitud de Traslado",
        description=(
            f"👤 Usuario: {interaction.user.mention}\n"
            f"🏢 Departamento actual: {rol_actual.mention}\n"
            f"➡️ Departamento solicitado: {rol_nuevo.mention}\n"
            f"📝 Razón: {razon}"
        ),
        color=discord.Color.orange()
    )

    await canal.send(embed=embed, view=TrasladoView(interaction.user, rol_actual, rol_nuevo))
    await interaction.response.send_message("📨 Solicitud de traslado enviada.", ephemeral=True)

@bot.tree.command(name="medalla")
@is_staff_superior()
async def medalla(interaction: discord.Interaction, usuario: discord.Member):
    canal = bot.get_channel(config.CANAL_MEDALLAS)

    await canal.send(
        content=usuario.mention,
        embed=discord.Embed(
            description="""🏅✨ ACTO DE RECONOCIMIENTO ESPECIAL ✨🏅

Hoy reconocemos una actuación ejemplar, marcada por el compromiso,
la valentía y la responsabilidad asumida en un momento crucial.

**Se le otorga oficialmente la Medalla Honorífica de Hispania MedCare.**""",
            color=discord.Color.gold()
        )
    )
    await interaction.response.send_message("🏅 Medalla otorgada.", ephemeral=True)

@bot.tree.command(name="reconocimiento-staff")
@is_staff_superior()
async def reconocimiento_staff(interaction: discord.Interaction, staff: discord.Member):
    canal = bot.get_channel(config.CANAL_RECONOCIMIENTOS)

    await canal.send(
        content=staff.mention,
        embed=discord.Embed(
            description="""🌟✨ RECONOCIMIENTO AL MEJOR STAFF DE LA SEMANA ✨🌟

Por su dedicación, compromiso y actitud ejemplar,
se le otorga oficialmente este reconocimiento.""",
            color=discord.Color.purple()
        )
    )
    await interaction.response.send_message("🌟 Reconocimiento enviado.", ephemeral=True)

@bot.tree.command(name="graduacion")
@is_staff_superior()
async def graduacion(interaction: discord.Interaction, usuario: discord.Member, rol: discord.Role):
    canal = bot.get_channel(config.CANAL_GRADUACIONES)

    await usuario.add_roles(rol)

    await canal.send(
        content=f"{usuario.mention} {rol.mention}",
        embed=discord.Embed(
            description="""🎓✨ ACTO DE GRADUACIÓN DE FACULTAD ✨🎓

Hoy celebramos el final de una etapa y el comienzo de una nueva trayectoria profesional.

🎓✨ **¡Enhorabuena!** ✨🎓""",
            color=discord.Color.blue()
        )
    )

    await interaction.response.send_message("🎓 Graduación registrada.", ephemeral=True)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    # Solo slash commands
    if interaction.type != discord.InteractionType.application_command:
        return

    canal = bot.get_channel(config.CANAL_LOGS_COMANDOS)
    if not canal:
        return

    embed = discord.Embed(
        title="📜 Log de Comando",
        color=discord.Color.dark_grey(),
        description=(
            f"👤 Usuario: {interaction.user} ({interaction.user.id})\n"
            f"📌 Comando: /{interaction.command.name}\n"
            f"📍 Canal: {interaction.channel.mention}\n"
            f"🕒 Fecha: <t:{int(interaction.created_at.timestamp())}:F>"
        )
    )

    await canal.send(embed=embed)

class EnviarDMModal(discord.ui.Modal, title="📨 Enviar Mensaje Directo"):
    id_objetivo = discord.ui.TextInput(
        label="ID del usuario o rol",
        placeholder="Ej: 123456789012345678",
        required=True,
        max_length=20
    )

    mensaje = discord.ui.TextInput(
        label="Mensaje",
        style=discord.TextStyle.paragraph,
        placeholder="Escribe aquí el mensaje que se enviará por DM",
        required=True,
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        enviados = 0
        fallidos = 0

        try:
            objetivo_id = int(self.id_objetivo.value)

            # 🔹 Intentar como usuario
            try:
                usuario = await interaction.client.fetch_user(objetivo_id)
                try:
                    await usuario.send(self.mensaje.value)
                    enviados += 1
                except discord.Forbidden:
                    fallidos += 1

            except:
                # 🔹 Si no es usuario, intentar como rol
                rol = interaction.guild.get_role(objetivo_id)
                if not rol:
                    await interaction.followup.send(
                        "❌ El ID no corresponde a un usuario ni a un rol.",
                        ephemeral=True
                    )
                    return

                for miembro in rol.members:
                    try:
                        await miembro.send(self.mensaje.value)
                        enviados += 1
                    except discord.Forbidden:
                        fallidos += 1

        except ValueError:
            await interaction.followup.send(
                "❌ El ID introducido no es válido.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📨 Envío de DM finalizado",
            color=discord.Color.orange(),
            description=(
                f"✅ Enviados: **{enviados}**\n"
                f"❌ Fallidos (DM cerrados): **{fallidos}**"
            )
        )
        embed.set_footer(text=f"Staff: {interaction.user}")

        await interaction.followup.send(embed=embed)

@bot.tree.command(name="enviar-dm", description="Enviar un DM a un usuario o rol mediante un formulario")
@is_staff_superior()
async def enviar_dm(interaction: discord.Interaction):
    await interaction.response.send_modal(EnviarDMModal())

@bot.tree.command(name="horario-semanal", description="Crear el horario semanal")
@is_staff_superior()
async def horario_semanal(interaction: discord.Interaction):
    canal = bot.get_channel(config.CANAL_HORARIO)
    if not canal:
        await interaction.response.send_message("❌ Canal de horario no encontrado.", ephemeral=True)
        return

    dias = [
        "Lunes", "Martes", "Miércoles",
        "Jueves", "Viernes", "Sábado", "Domingo"
    ]

    await canal.send(
        embed=discord.Embed(
            title="🗓️ HORARIO SEMANAL",
            description="Seleccione un día con `/dia-seleccionar` para asignar horario.",
            color=discord.Color.blue()
        )
    )

    for dia in dias:
        embed = discord.Embed(
            title=f"📅 {dia}",
            description="⏰ **Horario:** No asignado\n👤 **Responsable:** —",
            color=discord.Color.light_grey()
        )
        mensaje = await canal.send(embed=embed)
        HORARIO_EMBEDS[dia.lower()] = mensaje.id

    await interaction.response.send_message("✅ Horario semanal creado.", ephemeral=True)

@bot.tree.command(name="dia-seleccionar", description="Asignar horario a un día")
@is_staff_superior()
@app_commands.choices(dia=DIAS_CHOICES)
async def dia_seleccionar(
    interaction: discord.Interaction,
    dia: app_commands.Choice[str],
    hora: str,
    zona_horaria: str
):
    canal = bot.get_channel(config.CANAL_HORARIO)
    if not canal:
        await interaction.response.send_message("❌ Canal no encontrado.", ephemeral=True)
        return

    # ❌ Bloqueo si ya está reclamado
    if dia.value in HORARIO_ASIGNADO:
        await interaction.response.send_message(
            f"❌ El **{dia.name}** ya ha sido reclamado por <@{HORARIO_ASIGNADO[dia.value]}>.",
            ephemeral=True
        )
        return

    mensaje_id = HORARIO_EMBEDS.get(dia.value)
    if not mensaje_id:
        await interaction.response.send_message("❌ El horario no ha sido creado aún.", ephemeral=True)
        return

    mensaje = await canal.fetch_message(mensaje_id)

    embed = discord.Embed(
        title=f"📅 {dia.name}",
        description=(
            f"⏰ **Horario:** {hora} ({zona_horaria})\n"
            f"👤 **Responsable:** {interaction.user.mention}"
        ),
        color=discord.Color.green()
    )

    await mensaje.edit(embed=embed)

    # ✅ Guardar responsable
    HORARIO_ASIGNADO[dia.value] = interaction.user.id

    await interaction.response.send_message(
        f"✅ Has reclamado correctamente el **{dia.name}**.",
        ephemeral=True
    )

# ───── RUN ─────
bot.run(config.TOKEN)
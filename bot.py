import os
import sqlite3
import re
import discord
from discord.ext import commands

# =========================
# CONFIGURAÇÃO MEDELIN
# =========================
PAINEL_CHANNEL_ID = 1554539344331546736
APROVACAO_CHANNEL_ID = 1554547446091227217
MEMBRO_ROLE_ID = 1554539264035922000
RECRUTADOR_ROLE_ID = 1554540199143407787
TICKET_PANEL_CHANNEL_ID = 1554622852970324050
TICKET_CATEGORY_ID = 1554539334693294151
EQUIPE_ROLE_ID = 1554624015937577101
LOG_CHANNEL_ID = 1554539452339200090

IMAGE_FILE = "medelin.jpeg"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DB_FILE = "recrutamentos.db"

def iniciar_banco():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS recrutamentos (recrutador TEXT PRIMARY KEY COLLATE NOCASE, total INTEGER NOT NULL DEFAULT 0)")
        conn.commit()

def somar_recrutamento(nome):
    nome = nome.strip()
    if not nome: return
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("INSERT INTO recrutamentos(recrutador,total) VALUES(?,1) ON CONFLICT(recrutador) DO UPDATE SET total=total+1",(nome,))
        conn.commit()

def obter_ranking():
    with sqlite3.connect(DB_FILE) as conn:
        return conn.execute("SELECT recrutador,total FROM recrutamentos ORDER BY total DESC, recrutador ASC").fetchall()

iniciar_banco()


def tem_cargo(member: discord.Member, role_id: int) -> bool:
    return any(role.id == role_id for role in member.roles)


class RegistroModal(discord.ui.Modal, title="Registro | MEDELIN"):
    nome = discord.ui.TextInput(
        label="Nome",
        placeholder="Digite seu nome",
        max_length=40
    )
    id_jogador = discord.ui.TextInput(
        label="ID",
        placeholder="Digite seu ID",
        max_length=20
    )
    recrutador = discord.ui.TextInput(
        label="Quem recrutou",
        placeholder="Nome de quem te recrutou",
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        canal = interaction.guild.get_channel(APROVACAO_CHANNEL_ID)
        if canal is None:
            await interaction.response.send_message(
                "❌ O canal de aprovação não foi encontrado.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="👑 NOVO REGISTRO | MEDELIN 👑",
            description="Um novo registro está aguardando aprovação.",
            color=discord.Color.blue()
        )
        embed.add_field(name="👤 Nome", value=str(self.nome), inline=False)
        embed.add_field(name="🆔 ID", value=str(self.id_jogador), inline=False)
        embed.add_field(name="🤝 Quem recrutou", value=str(self.recrutador), inline=False)
        embed.add_field(
            name="📌 Discord",
            value=f"{interaction.user.mention}\n`{interaction.user.id}`",
            inline=False
        )
        embed.set_footer(text="MEDELIN • Sistema de Registro")

        await canal.send(
            embed=embed,
            view=AprovacaoView(
                membro_id=interaction.user.id,
                nome=str(self.nome),
                id_jogador=str(self.id_jogador),
                recrutador=str(self.recrutador)
            )
        )

        await interaction.response.send_message(
            "✅ Seu registro foi enviado!\n"
            "Agora aguarde a aprovação de um recrutador.",
            ephemeral=True
        )


class RegistroView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Registrar",
        emoji="📝",
        style=discord.ButtonStyle.primary,
        custom_id="medelin:registrar"
    )
    async def registrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegistroModal())


class AprovacaoView(discord.ui.View):
    def __init__(self, membro_id: int, nome: str, id_jogador: str, recrutador: str):
        # As aprovações individuais ficam ativas enquanto o bot estiver rodando.
        super().__init__(timeout=None)
        self.membro_id = membro_id
        self.nome = nome
        self.id_jogador = id_jogador
        self.recrutador = recrutador.strip()
        self.finalizado = False

    async def validar_recrutador(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member) or not tem_cargo(
            interaction.user, RECRUTADOR_ROLE_ID
        ):
            await interaction.response.send_message(
                "❌ Apenas quem possui o cargo de Recrutador pode aprovar ou recusar registros.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Aprovar", emoji="✅", style=discord.ButtonStyle.success)
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.validar_recrutador(interaction):
            return

        if self.finalizado:
            await interaction.response.send_message(
                "⚠️ Este registro já foi finalizado.", ephemeral=True
            )
            return

        membro = interaction.guild.get_member(self.membro_id)
        if membro is None:
            try:
                membro = await interaction.guild.fetch_member(self.membro_id)
            except discord.NotFound:
                await interaction.response.send_message(
                    "❌ Esse membro não está mais no servidor.", ephemeral=True
                )
                return

        cargo = interaction.guild.get_role(MEMBRO_ROLE_ID)
        if cargo is None:
            await interaction.response.send_message(
                "❌ O cargo de Membro não foi encontrado.", ephemeral=True
            )
            return

        try:
            await membro.add_roles(
                cargo, reason=f"Registro aprovado por {interaction.user}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não consegui adicionar o cargo. Coloque o cargo do bot acima do cargo Membro.",
                ephemeral=True
            )
            return

        # Tenta alterar o apelido, mas não impede a aprovação se não tiver permissão.
        try:
            novo_nick = f"{self.nome} | {self.id_jogador}"[:32]
            await membro.edit(
                nick=novo_nick,
                reason=f"Registro aprovado por {interaction.user}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        somar_recrutamento(self.recrutador)
        self.finalizado = True
        for item in self.children:
            item.disabled = True

        embed = interaction.message.embeds[0].copy()
        embed.title = "✅ REGISTRO APROVADO | MEDELIN"
        embed.color = discord.Color.green()
        embed.add_field(
            name="✅ Aprovado por",
            value=interaction.user.mention,
            inline=False
        )

        await interaction.response.edit_message(embed=embed, view=self)

        try:
            await membro.send(
                f"✅ Seu registro na **MEDELIN** foi aprovado por **{interaction.user.display_name}**."
            )
        except discord.Forbidden:
            pass

    @discord.ui.button(label="Recusar", emoji="❌", style=discord.ButtonStyle.danger)
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.validar_recrutador(interaction):
            return

        if self.finalizado:
            await interaction.response.send_message(
                "⚠️ Este registro já foi finalizado.", ephemeral=True
            )
            return

        self.finalizado = True
        for item in self.children:
            item.disabled = True

        embed = interaction.message.embeds[0].copy()
        embed.title = "❌ REGISTRO RECUSADO | MEDELIN"
        embed.color = discord.Color.red()
        embed.add_field(
            name="❌ Recusado por",
            value=interaction.user.mention,
            inline=False
        )

        await interaction.response.edit_message(embed=embed, view=self)

        membro = interaction.guild.get_member(self.membro_id)
        if membro:
            try:
                await membro.send(
                    f"❌ Seu registro na **MEDELIN** foi recusado por "
                    f"**{interaction.user.display_name}**.\n"
                    "Você pode realizar um novo registro."
                )
            except discord.Forbidden:
                pass



@bot.command(name="ranking")
async def ranking(ctx):
    dados = obter_ranking()
    embed = discord.Embed(title="🏆 RANKING DE RECRUTADORES | MEDELIN", color=discord.Color.blue())
    if not dados:
        embed.description = "Ainda não há recrutamentos aprovados."
    else:
        linhas=[]
        for i,(nome,total) in enumerate(dados[:20],1):
            p = ["🥇","🥈","🥉"][i-1] if i <= 3 else f"`{i}º`"
            linhas.append(f"{p} **{nome}** — **{total}** recrutamento(s)")
        embed.description="\\n".join(linhas)
    embed.set_footer(text="MEDELIN • Apenas registros aprovados são contabilizados")
    await ctx.send(embed=embed)

@bot.command(name="recs")
async def recs(ctx, *, nome: str = None):
    if not nome:
        await ctx.send("Use: `!recs Nome do recrutador`")
        return
    with sqlite3.connect(DB_FILE) as conn:
        r=conn.execute("SELECT recrutador,total FROM recrutamentos WHERE recrutador=? COLLATE NOCASE",(nome.strip(),)).fetchone()
    if r:
        await ctx.send(f"📊 **{r[0]}** possui **{r[1]}** recrutamento(s) aprovado(s).")
    else:
        await ctx.send(f"📊 **{nome.strip()}** ainda não possui recrutamentos aprovados.")


class ConfirmarResetRanking(discord.ui.View):
    def __init__(self, autor_id: int):
        super().__init__(timeout=30)
        self.autor_id = autor_id

    @discord.ui.button(label="Confirmar reset", emoji="⚠️", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message(
                "❌ Somente quem executou o comando pode confirmar.",
                ephemeral=True
            )
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem resetar o ranking.",
                ephemeral=True
            )
            return

        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("DELETE FROM recrutamentos")
            conn.commit()

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content="✅ **Ranking de recrutadores resetado com sucesso!**",
            view=self
        )

    @discord.ui.button(label="Cancelar", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message(
                "❌ Somente quem executou o comando pode cancelar.",
                ephemeral=True
            )
            return

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content="❌ Reset do ranking cancelado.",
            view=self
        )


@bot.command(name="resetaranking")
@commands.has_permissions(administrator=True)
async def resetaranking(ctx):
    await ctx.send(
        "⚠️ **Tem certeza que deseja zerar TODO o ranking de recrutadores?**\n"
        "Essa ação apaga todas as contagens atuais.",
        view=ConfirmarResetRanking(ctx.author.id)
    )


@resetaranking.error
async def resetaranking_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Apenas administradores podem usar `!resetaranking`.")
    else:
        raise error


def nome_canal(usuario: discord.Member):
    nome = usuario.display_name.lower()
    nome = re.sub(r"[^a-z0-9-]", "-", nome)
    nome = re.sub(r"-+", "-", nome).strip("-")
    return f"ticket-{nome or usuario.id}"[:90]


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Abrir Ticket",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id="medelin:abrir_ticket"
    )
    async def abrir_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        categoria = guild.get_channel(TICKET_CATEGORY_ID)
        equipe = guild.get_role(EQUIPE_ROLE_ID)

        if categoria is None or not isinstance(categoria, discord.CategoryChannel):
            await interaction.response.send_message(
                "❌ A categoria de tickets não foi encontrada.", ephemeral=True
            )
            return

        if equipe is None:
            await interaction.response.send_message(
                "❌ O cargo da equipe não foi encontrado.", ephemeral=True
            )
            return

        # Evita vários tickets abertos pela mesma pessoa.
        for canal in categoria.text_channels:
            if canal.topic == f"ticket_owner:{interaction.user.id}":
                await interaction.response.send_message(
                    f"⚠️ Você já possui um ticket aberto: {canal.mention}",
                    ephemeral=True
                )
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
            equipe: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
                attach_files=True,
                embed_links=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_permissions=True
            )
        }

        try:
            canal = await guild.create_text_channel(
                name=nome_canal(interaction.user),
                category=categoria,
                overwrites=overwrites,
                topic=f"ticket_owner:{interaction.user.id}",
                reason=f"Ticket aberto por {interaction.user}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ O bot não tem permissão para criar canais nessa categoria.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎫 TICKET | MEDELIN",
            description=(
                f"Olá {interaction.user.mention}! 💙🤍\n\n"
                "Seu ticket foi criado com sucesso.\n"
                "Explique abaixo o motivo do contato e aguarde um membro da equipe.\n\n"
                "⚠️ Evite marcar a equipe várias vezes.\n"
                "Quando o atendimento terminar, use o botão **🔒 Fechar Ticket**."
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="MEDELIN • Respeito, união e lealdade.")

        await canal.send(
            content=f"{interaction.user.mention} {equipe.mention}",
            embed=embed,
            view=TicketControlView()
        )

        logs = guild.get_channel(LOG_CHANNEL_ID)
        if logs:
            log_embed = discord.Embed(
                title="🎫 Ticket aberto",
                color=discord.Color.green()
            )
            log_embed.add_field(name="Usuário", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
            log_embed.add_field(name="Canal", value=canal.mention, inline=False)
            await logs.send(embed=log_embed)

        await interaction.response.send_message(
            f"✅ Seu ticket foi criado: {canal.mention}",
            ephemeral=True
        )


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Fechar Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="medelin:fechar_ticket"
    )
    async def fechar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal = interaction.channel
        guild = interaction.guild
        equipe = guild.get_role(EQUIPE_ROLE_ID)

        owner_id = None
        if canal.topic and canal.topic.startswith("ticket_owner:"):
            try:
                owner_id = int(canal.topic.split(":", 1)[1])
            except ValueError:
                pass

        pode_fechar = (
            interaction.user.id == owner_id
            or (equipe is not None and equipe in interaction.user.roles)
            or interaction.user.guild_permissions.administrator
        )

        if not pode_fechar:
            await interaction.response.send_message(
                "❌ Você não pode fechar este ticket.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "🔒 Ticket encerrado. Este canal será apagado em alguns segundos."
        )

        logs = guild.get_channel(LOG_CHANNEL_ID)
        if logs:
            log_embed = discord.Embed(
                title="🔒 Ticket fechado",
                color=discord.Color.red()
            )
            log_embed.add_field(name="Canal", value=f"`{canal.name}`", inline=False)
            log_embed.add_field(name="Fechado por", value=interaction.user.mention, inline=False)
            if owner_id:
                log_embed.add_field(name="Dono do ticket", value=f"<@{owner_id}>", inline=False)
            await logs.send(embed=log_embed)

        import asyncio
        await asyncio.sleep(5)
        try:
            await canal.delete(reason=f"Ticket fechado por {interaction.user}")
        except discord.Forbidden:
            pass


async def enviar_painel_ticket():
    canal = bot.get_channel(TICKET_PANEL_CHANNEL_ID)
    if canal is None:
        print("ERRO: canal do painel não encontrado.")
        return

    async for msg in canal.history(limit=100):
        if msg.author.id == bot.user.id and msg.embeds:
            if msg.embeds[0].title == "🎫 CENTRAL DE TICKETS | MEDELIN":
                print("Painel de tickets já existe.")
                return

    embed = discord.Embed(
        title="🎫 CENTRAL DE TICKETS | MEDELIN",
        description=(
            "Seja bem-vindo(a) ao suporte da **MEDELIN**! 💙🤍\n\n"
            "Caso precise falar com nossa equipe, clique no botão "
            "**「🎫 Abrir Ticket」** abaixo.\n\n"
            "📌 **Antes de abrir:**\n"
            "• Explique claramente o motivo do contato.\n"
            "• Abra apenas **um ticket por vez**.\n"
            "• Aguarde a equipe responder ao atendimento.\n"
            "• Não abra tickets sem necessidade.\n\n"
            "🔒 O ticket será privado entre você e a equipe da MEDELIN.\n\n"
            "💙 **MEDELIN — Respeito, união e lealdade.** 🤍"
        ),
        color=discord.Color.blue()
    )

    try:
        arquivo = discord.File(IMAGE_FILE, filename="medelin.jpeg")
        embed.set_image(url="attachment://medelin.jpeg")
        await canal.send(file=arquivo, embed=embed, view=TicketView())
    except FileNotFoundError:
        await canal.send(embed=embed, view=TicketView())

    print("Painel de tickets enviado.")



async def enviar_painel():
    canal = bot.get_channel(PAINEL_CHANNEL_ID)
    if canal is None:
        print("ERRO: Canal do painel não encontrado.")
        return

    # Evita duplicar o painel a cada reinício.
    async for msg in canal.history(limit=100):
        if msg.author.id == bot.user.id and msg.embeds:
            if msg.embeds[0].title == "👑 REGISTRO | MEDELIN 👑":
                print("Painel já existe no canal.")
                return

    descricao = """Seja bem-vindo(a) à **MEDELIN!** 💙🤍

Para realizar seu registro, clique no botão 「📝 **Registrar**」 abaixo e preencha corretamente:

👤 **Nome:**
🆔 **ID:**
🤝 **Quem recrutou:**

Após o envio, seu registro ficará aguardando aprovação de um recrutador.

✅ **Registro aprovado:** você receberá automaticamente o cargo de Membro.
❌ **Registro recusado:** será necessário realizar um novo registro.

⚠️ Não coloque informações falsas e não envie o registro mais de uma vez.

💙 **MEDELIN — Respeito, união e lealdade.** 🤍"""

    embed = discord.Embed(
        title="👑 REGISTRO | MEDELIN 👑",
        description=descricao,
        color=discord.Color.blue()
    )

    arquivo = discord.File(IMAGE_FILE, filename="medelin.jpeg")
    embed.set_image(url="attachment://medelin.jpeg")

    await canal.send(file=arquivo, embed=embed, view=RegistroView())
    print("Painel enviado com sucesso.")


@bot.event
async def on_ready():
    # Mantém os botões principais funcionando após reinícios.
    bot.add_view(RegistroView())
    bot.add_view(TicketView())
    bot.add_view(TicketControlView())
    print(f"Bot MEDELIN conectado como {bot.user} ({bot.user.id})")
    await enviar_painel()
    await enviar_painel_ticket()


TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "Defina a variável de ambiente DISCORD_TOKEN com o token do seu bot."
    )

bot.run(TOKEN)

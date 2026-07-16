import discord


def is_admin(interaction: discord.Interaction) -> bool:
    perms = interaction.user.guild_permissions if hasattr(interaction.user, "guild_permissions") else None
    return bool(perms and (perms.administrator or perms.manage_guild))

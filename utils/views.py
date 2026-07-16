import discord


def youtube_video_view(url: str) -> discord.ui.View:
    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="▶️ Otevřít na YouTube",
            url=url,
        )
    )
    return view

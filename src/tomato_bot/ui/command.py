from __future__ import annotations

__all__ = ("register_global_commands",)

from textwrap import dedent
from typing import TYPE_CHECKING, Final

import discord
from discord import app_commands

from tomato_bot.application.command_use_case import (
    AlreadyStarted,
    AlreadyStarting,
    CommandUseCase,
)
from tomato_bot.application.session_manager import (
    SessionNotFound,
)
from tomato_bot.config import override_about_text, override_help_text
from tomato_bot.domain import TimerAlreadyPaused, TimerAlreadyResumed, TimerNotStarted
from tomato_bot.ui.common_text import REQUIRE_VC_TEXT
from tomato_bot.ui.view import JoinSelectRoutineView
from tomato_bot.utils import command_mention

if TYPE_CHECKING:
    from tomato_bot.bot import TomatoBot


@app_commands.command(
    name="ポモドーロタイマーを開始",
    description="あなたが参加しているVCに接続し、ポモドーロタイマーを作動します。",
)
@app_commands.guild_only()
async def start(interaction: discord.Interaction[TomatoBot]) -> None:
    """ポモドーロタイマー機能をユーザーのVCで開始するコマンド"""
    member = interaction.user
    assert isinstance(member, discord.Member)
    text_channel = interaction.channel
    assert isinstance(text_channel, discord.abc.Messageable)

    # VCにユーザーが接続しているか確認する。
    if member.voice is None or member.voice.channel is None:
        await interaction.response.send_message(REQUIRE_VC_TEXT, ephemeral=True)
        return

    # ポモドーロタイマーで動かすroutineを選択してもらう。
    use_case = get_use_case(interaction)

    try:
        flow = await use_case.begin_start_flow(member.guild.id, member.id)
    except AlreadyStarting as e:
        content = (
            "既にポモドーロタイマーの開始操作が以下のメッセージで行われているようです。"
        )

        jump_url = e.start_prompt_jump_url
        if jump_url is not None:
            content += f"\nこちらをご確認ください: {jump_url}"

        await interaction.response.send_message(content, ephemeral=True)
        return
    except AlreadyStarted:
        await interaction.response.send_message(
            "既にポモドーロタイマーは動作しているようです。なので何もしませんでした。",
            ephemeral=True,
        )
        return

    response = await interaction.response.send_message(
        "ポモドーロタイマーのルーチンを選択してください。",
        view=JoinSelectRoutineView(
            dict(flow.routines),
            use_case=use_case,
            target_user_id=member.id,
            text_channel=text_channel,
            voice_channel=member.voice.channel,
        ),
    )

    if isinstance(response.resource, discord.InteractionMessage):
        jump_url = response.resource.jump_url
    else:
        jump_url = (await interaction.original_response()).jump_url

    use_case.attach_start_prompt_jump_url(flow.guild_id, jump_url)


@app_commands.command(
    name="ポモドーロタイマーを終了",
    description="あなたが参加しているVCでのポモドーロタイマーを終了します。",
)
@app_commands.guild_only()
async def stop(interaction: discord.Interaction[TomatoBot]) -> None:
    """ポモドーロタイマーの動作を停止するコマンド"""
    assert isinstance(interaction.guild, discord.Guild)

    use_case = get_use_case(interaction)
    try:
        await use_case.stop(interaction.guild.id)
    except SessionNotFound:
        await interaction.response.send_message(
            "既にポモドーロタイマーはあなたのVCで稼働していないようです。"
            "したがって、私は何もしませんでした。"
            "\n-# もしタイマーは動いていないがVCに残ってしまっている場合、"
            "`/強制退出`を使ってみてください。"
        )
    else:
        await interaction.response.send_message("ポモドーロタイマーを終了しました。")


@app_commands.command(
    name="強制退出",
    description="ポモドーロタイマーが稼働してるかどうかに関係なく、"
    "VCから強制的にトマトBotを退出させます。",
)
@app_commands.guild_only()
async def force_disconnect(interaction: discord.Interaction[TomatoBot]) -> None:
    """強制的にVCからBotを切断させるコマンド"""
    assert isinstance(interaction.guild, discord.Guild)

    use_case = get_use_case(interaction)
    try:
        await use_case.stop(interaction.guild.id, force=True)
    except SessionNotFound:
        # セッションマネージャもセッションを知らない場合、
        # 最低限VCからは強制退出させる。
        if interaction.guild.voice_client is not None:
            await interaction.guild.voice_client.disconnect(force=True)

    await interaction.response.send_message(
        "強制退出を指示されたので、VCから退出しました。"
    )


@app_commands.command(
    name="ポモドーロタイマーを一時停止",
    description="ポモドーロタイマーを一時的に停止します。",
)
@app_commands.guild_only()
async def pause(interaction: discord.Interaction[TomatoBot]) -> None:
    """ポモドーロタイマーを一時停止するコマンド"""
    assert isinstance(interaction.guild, discord.Guild)

    use_case = get_use_case(interaction)
    try:
        use_case.pause(interaction.guild.id)
    except SessionNotFound:
        await interaction.response.send_message(
            "ポモドーロタイマーは現在動いていないようです。なので何もしませんでした。",
            ephemeral=True,
        )
    except TimerNotStarted:
        await interaction.response.send_message(
            "ポモドーロタイマーはまだ開始していません。なので何もしませんでした。",
            ephemeral=True,
        )
    except TimerAlreadyPaused:
        await interaction.response.send_message(
            "ポモドーロタイマーは既に一時停止中です。なので何もしませんでした。",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "ポモドーロタイマーを一時停止しました。"
        )


@app_commands.command(
    name="ポモドーロタイマーを再開",
    description="一時停止したポモドーロタイマーを再開します。",
)
@app_commands.guild_only()
async def resume(interaction: discord.Interaction[TomatoBot]) -> None:
    """ポモドーロタイマーを再開するコマンド"""
    assert isinstance(interaction.guild, discord.Guild)

    use_case = get_use_case(interaction)
    try:
        use_case.resume(interaction.guild.id)
    except SessionNotFound:
        await interaction.response.send_message(
            "ポモドーロタイマーは現在動いていないようです。なので何もしませんでした。",
            ephemeral=True,
        )
    except TimerNotStarted:
        # use_case.start(interaction.guild)
        # TODO: ここでフォールバックとして、開始ボタンを押したこととするか検討する。
        await interaction.response.send_message(
            "ポモドーロタイマーはまだ開始していません。「開始！」ボタンを押す必要があります。",
            ephemeral=True,
        )
    except TimerAlreadyResumed:
        await interaction.response.send_message(
            "ポモドーロタイマーは既に動いています。なので何もしませんでした。",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message("ポモドーロタイマーを再開しました。")


@app_commands.command(
    name="このボットについて", description="このBotの説明を表示します。"
)
async def about(interaction: discord.Interaction[TomatoBot]) -> None:
    """このBotに関する情報を表示するコマンド"""
    ABOUT_TEXT: Final = dedent(
        """
        このBotは、メッセージとアラーム音でポモドーロタイマーをVCで動かせるBotです。
        現在クローズドベータで一部先行公開中です。

        {start}でタイマーを開始、{stop}で停止ができます。
        その他、詳細なコマンド一覧は{help}をご確認くださいませ。

        - クレジット:
          - デフォルトのアラーム音: [OtoLogic](<https://otologic.jp>) (CC BY 4.0)
        - リポジトリ: [tasuren/tomato-bot](<https://github.com/tasuren/tomato-bot>)
        - 問い合わせ先（DM）: [`tasuren`](<https://discord.com/users/634763612535390209>)
        """
    )[1:-1]

    commands = await retrieve_commands(interaction.client)
    start_command = command_mention(commands[start.name])
    stop_command = command_mention(commands[stop.name])
    help_command = command_mention(commands[help.name])

    await interaction.response.send_message(
        (override_about_text() or ABOUT_TEXT).format(
            start=start_command,
            stop=stop_command,
            help=help_command,
        )
    )


@app_commands.command(
    name="使い方", description="このBotのコマンド一覧を表示し、使い方を説明します。"
)
async def help(interaction: discord.Interaction[TomatoBot]) -> None:
    """このBotの使い方を説明するコマンド"""
    HELP_TEXT: Final = dedent(
        """
        🍅 トマトBot
        このBotはポモドーロタイマーをVCで動かし、メッセージとアラームでフェーズをお知らせするBotです。

        **基本的な使い方**
        - {start}
        - {stop}

        **その他、機能**
        - {pause}
        - {resume}
        - バグでVCに残ってしまった時: {force_disconnect}

        以上が使い方となります。
        Bot自体の情報は{about}で確認ができます。
        """
    )[1:-1]

    commands = await retrieve_commands(interaction.client)
    start_command = command_mention(commands[start.name])
    stop_command = command_mention(commands[stop.name])
    pause_command = command_mention(commands[pause.name])
    resume_command = command_mention(commands[resume.name])
    force_disconnect_command = command_mention(commands[force_disconnect.name])
    about_command = command_mention(commands[about.name])

    await interaction.response.send_message(
        (override_help_text() or HELP_TEXT).format(
            start=start_command,
            stop=stop_command,
            pause=pause_command,
            resume=resume_command,
            force_disconnect=force_disconnect_command,
            about=about_command,
        )
    )


def get_use_case(interaction: discord.Interaction[TomatoBot]) -> CommandUseCase:
    return interaction.client.application_services.command_use_case


_command_cache: dict[str, app_commands.AppCommand] | None = None


async def retrieve_commands(bot: TomatoBot) -> dict[str, app_commands.AppCommand]:
    """コマンドの情報を取得する。"""
    global _command_cache

    if _command_cache is None:
        commands = await bot.tree.fetch_commands()
        _command_cache = {cmd.name: cmd for cmd in commands}

    return _command_cache


def register_global_commands(bot: TomatoBot) -> None:
    """Botにコマンドを登録する。"""
    bot.tree.add_command(start)
    bot.tree.add_command(stop)
    bot.tree.add_command(force_disconnect)
    bot.tree.add_command(pause)
    bot.tree.add_command(resume)
    bot.tree.add_command(about)
    bot.tree.add_command(help)

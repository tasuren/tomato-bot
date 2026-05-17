from __future__ import annotations

__all__ = ("JoinSelectRoutineView",)

from collections.abc import Iterable
from typing import TYPE_CHECKING, Self, override

import discord

from tomato_bot.application.command_use_case import CommandUseCase
from tomato_bot.application.session_manager import (
    SessionAlreadyCreated,
    SessionNotFound,
    TimerAlreadyStarted,
)
from tomato_bot.config import loading_emoji
from tomato_bot.domain import Routine
from tomato_bot.ui.command_info import retrieve_commands
from tomato_bot.utils import command_mention, normalize_nested_quotes

if TYPE_CHECKING:
    from tomato_bot.bot import TomatoBot


class SelectRoutineView(discord.ui.View):
    """ルーチンを選択するためのview"""

    def __init__(self, routines: Iterable[Routine]) -> None:
        super().__init__()

        for routine in routines:
            self.routine_select.add_option(
                label=routine.name,
                description="{user_preference}{routine_description}".format(
                    user_preference="ユーザー設定: "
                    if routine.is_user_preference
                    else "",
                    routine_description=routine.description,
                ),
                value=str(routine.id),
            )

    @discord.ui.select(placeholder="ルーチンを選択")
    async def routine_select(
        self,
        interaction: discord.Interaction[TomatoBot],
        select: discord.ui.Select[Self],
    ) -> None:
        """ルーチン選択コンポーネント"""
        await self.on_select(interaction, int(select.values[0]))

    async def on_select(
        self, interaction: discord.Interaction[TomatoBot], selected_routine_id: int
    ) -> None:
        """ルーチンが選択された際に呼ばれる関数"""
        raise NotImplementedError


class StartConfirmView(discord.ui.View):
    """ルーチン確定後にタイマー開始を確認するview"""

    def __init__(self, *, use_case: CommandUseCase, guild_id: int) -> None:
        super().__init__()

        self._use_case = use_case
        self._guild_id = guild_id

    @discord.ui.button(style=discord.ButtonStyle.primary, label="開始！", emoji="🍅")
    async def start(
        self, interaction: discord.Interaction[TomatoBot], _: discord.ui.Button
    ) -> None:
        self.stop()
        self._disable_buttons()

        content = None
        try:
            self._use_case.start(self._guild_id)
        except SessionNotFound:
            commands = await retrieve_commands(interaction.client)
            start = command_mention(commands["ポモドーロタイマーを開始"])
            content = (
                "別で停止コマンドが使われたため、開始できませんでした。\n"
                f"もう一度、{start}コマンドを使ってみてください。"
            )
        except TimerAlreadyStarted:
            content = (
                "既にポモドーロタイマーは動作しています。なので何もしませんでした。"
            )

        if content is None:
            await interaction.response.edit_message(view=self)
        else:
            # エラー時は編集を応答にせず、エラー返信を応答にする。
            if interaction.message is not None:
                await interaction.message.edit(view=self)
            await interaction.response.send_message(content=content)

    @discord.ui.button(style=discord.ButtonStyle.secondary, label="やっぱやめる")
    async def cancel(
        self, interaction: discord.Interaction[TomatoBot], _: discord.ui.Button
    ) -> None:
        self.stop()
        await self._use_case.cancel_start(self._guild_id)

        self._disable_buttons()
        await interaction.response.edit_message(view=self)

        if interaction.message is not None:
            await interaction.message.reply("キャンセルしました。")

    @override
    async def on_timeout(self) -> None:
        await self._use_case.cancel_start(self._guild_id)

    def _disable_buttons(self) -> None:
        self.start.disabled = True
        self.cancel.disabled = True


class JoinSelectRoutineView(SelectRoutineView):
    """joinコマンドのためのルーチン選択view"""

    def __init__(
        self,
        routines: dict[int, Routine],
        *,
        use_case: CommandUseCase,
        guild_id: int,
        target_user_id: int,
        text_channel: discord.abc.Messageable,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
    ) -> None:
        super().__init__(routines.values())

        self._routines = routines
        self._use_case = use_case
        self._guild_id = guild_id
        self._text_channel = text_channel
        self._voice_channel = voice_channel
        self._target_user_id = target_user_id

    @override
    async def on_timeout(self) -> None:
        await self._use_case.cancel_start(self._guild_id)

    @override
    async def on_select(
        self, interaction: discord.Interaction[TomatoBot], selected_routine_id: int
    ) -> None:
        if interaction.user.id != self._target_user_id:
            await interaction.response.send_message(
                "コマンドを実行した人ではないので、あなたはルーチンを選択できません。",
                ephemeral=True,
            )
            return

        member = interaction.user
        assert isinstance(member, discord.Member)
        self.stop()

        # 接続処理やデータベースからの読み込みで遅延する恐れがあるので、
        # 念の為deferして応答を遅らせる。
        self.routine_select.disabled = True
        if interaction.message is None:
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.edit_message(
                content=interaction.message.content + f" {loading_emoji()}", view=self
            )

        # ルーチンを確定してポモドーロタイマーを準備する。
        routine = self._routines[selected_routine_id]
        try:
            await self._use_case.prepare_start(
                routine,
                text_channel=self._text_channel,
                voice_channel=self._voice_channel,
            )
        except SessionAlreadyCreated:
            await interaction.edit_original_response(
                content="既にポモドーロタイマーは別で設定済みのようです。"
                "なので何もしませんでした。",
                view=None,
            )
            return

        # 即座にタイマーは稼働させずに、ユーザーからボタンを押されたタイミングにする。
        confirm_view = StartConfirmView(
            use_case=self._use_case,
            guild_id=member.guild.id,
        )

        routine_display_name = normalize_nested_quotes(routine.name)
        await interaction.edit_original_response(
            content=f"準備が完了しました。\nポモドーロタイマーを「{routine_display_name}」で開始します。",
            view=confirm_view,
        )

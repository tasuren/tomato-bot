from __future__ import annotations

from tomato_bot.config import loading_emoji

__all__ = ("JoinSelectRoutineView",)

from collections.abc import Iterable
from typing import TYPE_CHECKING, Self, override

import discord

from tomato_bot.application.command_use_case import CommandUseCase
from tomato_bot.application.session_manager import (
    SessionAlreadyCreated,
    TimerAlreadyStarted,
)
from tomato_bot.domain import Routine
from tomato_bot.utils import normalize_nested_quotes

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


class JoinSelectRoutineView(SelectRoutineView):
    """joinコマンドのためのルーチン選択view"""

    def __init__(
        self,
        routines: dict[int, Routine],
        *,
        use_case: CommandUseCase,
        target_user_id: int,
        text_channel: discord.abc.Messageable,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
    ) -> None:
        super().__init__(routines.values())

        self._routines = routines
        self._use_case = use_case
        self._text_channel = text_channel
        self._voice_channel = voice_channel
        self._target_user_id = target_user_id

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
            ALREADY_STARTED = "既にポモドーロタイマーは設定済みのようです。"

            if interaction.message is None:
                await interaction.edit_original_response(content=ALREADY_STARTED)
            else:
                await interaction.message.reply(ALREADY_STARTED)

            return

        # 即座にタイマーは稼働させずに、ユーザーからボタンを押されたタイミングにする。
        confirm_view = discord.ui.View()
        start_button = discord.ui.Button(
            style=discord.ButtonStyle.primary, label="開始！", emoji="🍅"
        )
        stop_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="やっぱやめる"
        )

        async def start(interaction: discord.Interaction[TomatoBot]) -> None:
            try:
                self._use_case.start(member.guild.id)
            except TimerAlreadyStarted:
                await interaction.response.send_message(
                    "既にポモドーロタイマーは動作しています。"
                    "なので何もしませんでした。",
                    ephemeral=True,
                )
                return

            start_button.disabled = True
            stop_button.disabled = True
            await interaction.response.edit_message(view=confirm_view)

        async def stop(interaction: discord.Interaction[TomatoBot]) -> None:
            await self._use_case.cancel_start(member.guild.id)
            start_button.disabled = True
            stop_button.disabled = True
            await interaction.response.edit_message(view=confirm_view)
            if interaction.message is not None:
                await interaction.message.reply("キャンセルしました。")

        start_button.callback = start
        stop_button.callback = stop
        confirm_view.add_item(start_button)
        confirm_view.add_item(stop_button)

        routine_display_name = normalize_nested_quotes(routine.name)
        await interaction.edit_original_response(
            content=f"準備が完了しました。ポモドーロタイマーを「{routine_display_name}」で開始します。",
            view=confirm_view,
        )

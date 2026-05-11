"""discord.pyでwavファイルを再生するための実装。

参考: https://github.com/tasuren/dpy-wav-sample/
"""

from __future__ import annotations

__all__ = ("WavAudio",)

from typing import IO
import wave

from discord.opus import Encoder as OpusEncoder
import discord
import audioop

class WavAudio(discord.AudioSource):
    """Wavファイル形式のデータを再生するための、``AudioSource``の実装。"""

    def __init__(self, stream: IO[bytes]) -> None:
        self._wav: wave.Wave_read = wave.open(stream)

        # wavファイルの情報を取得する。

        # sampling_rate: サンプリングレート、１秒間にいくつのサンプルがあるか。
        # samples_per_frame: 20msのデータのサンプル数
        # sample_size: 一つのサンプルが何バイトか
        # frame_size: 20msが何バイトになるか

        sampling_rate = self._wav.getframerate()
        self.samples_per_frame = int(sampling_rate / 1000 * OpusEncoder.FRAME_LENGTH)
        self.sample_size = self._wav.getsampwidth() * self._wav.getnchannels()
        self.frame_size = self.samples_per_frame * self.sample_size

        # 音声の変換で使う状態
        self._is_first = True
        self._ratecv_state = None

    def read(self) -> bytes:
        # `discord.AudioSource`が20msのデータ欲しているので、20ms分のデータを読み込む。
        samples = self._wav.readframes(self.samples_per_frame)

        # `discord.AudioSource`は16ビットの48kHzのステレオ音声である必要がある。
        # そのため、それに変換を行う。
        samples = self._convert_dpy_specific(samples)

        # 音声が適切に20ms分足りるか確認する。
        if len(samples) != OpusEncoder.FRAME_SIZE:
            if self._is_first:
                # データを読み込むのが初回の場合、サンプリングレートの変換の仕様上、少しデータの最が欠ける。
                # そのため、無音データを挟む
                lack_bytes = OpusEncoder.FRAME_SIZE - len(samples)
                samples = bytes(lack_bytes) + samples

                self._is_first = False
            elif len(samples) > 0:
                # データを読み込むのが最初ではないが、データ数が20ms分に達しない場合、音声の最後。
                # そのため、無音データを後ろに挟んで20msにする。
                lack_bytes = OpusEncoder.FRAME_SIZE - len(samples)
                samples += bytes(lack_bytes)

        return samples

    def _convert_dpy_specific(self, samples: bytes) -> bytes:
        """渡されたPCM音声データを、`discord.AudioSource`の要求する形に変更する。"""
        SAMPLE_WIDTH_8BIT = 1  # 1バイト
        SAMPLE_WIDTH_16BIT = 2  # 2バイト

        # 16ビットにする。
        if self._wav.getsampwidth() != SAMPLE_WIDTH_16BIT:
            previous_width = self._wav.getsampwidth()

            # wavの8ビットは符号無しだが、16、24、そして32ビットの場合符号付き。ただ、8ビットも符号付きで扱いたい。
            # そのため、もしwavファイルが8ビットなら、0~255ではなく-128~127の範囲にする必要がある。
            if previous_width == SAMPLE_WIDTH_8BIT:
                samples = audioop.bias(samples, SAMPLE_WIDTH_8BIT, -128)

            samples = audioop.lin2lin(samples, previous_width, SAMPLE_WIDTH_16BIT)

        # 48kHzにする。
        if self._wav.getframerate() != OpusEncoder.SAMPLING_RATE:
            samples, self._ratecv_state = audioop.ratecv(
                samples,
                SAMPLE_WIDTH_16BIT,
                self._wav.getnchannels(),
                self._wav.getframerate(),
                OpusEncoder.SAMPLING_RATE,
                self._ratecv_state,
            )

        # ステレオにする。
        if self._wav.getnchannels() != OpusEncoder.CHANNELS:
            samples = audioop.tostereo(samples, SAMPLE_WIDTH_16BIT, 1.0, 1.0)

        return samples

    def cleanup(self) -> None:
        self._wav.close()
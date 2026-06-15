"""Frequency-domain image watermarking helpers.

The implementation embeds UTF-8 text in 8x8 DCT blocks. It is blind
watermarking: extraction needs the same key, but not the original image.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import random
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image


BLOCK_SIZE = 8
MAGIC = b"FWM1"
HEADER_BYTES = len(MAGIC) + 2
HEADER_BITS = HEADER_BYTES * 8
COEFF_A = (3, 2)
COEFF_B = (2, 3)

ProgressCallback = Callable[[int, int], None]


class WatermarkError(Exception):
    """Raised when an image cannot be watermarked or decoded."""


@dataclass(frozen=True)
class Capacity:
    width: int
    height: int
    capacity_bits: int
    max_text_bytes: int


@dataclass(frozen=True)
class EmbedResult:
    output_path: Path
    text_bytes: int
    used_bits: int
    capacity_bits: int


@dataclass(frozen=True)
class ExtractResult:
    message: str
    text_bytes: int
    used_bits: int
    capacity_bits: int


def image_capacity(width: int, height: int) -> Capacity:
    capacity_bits = (width // BLOCK_SIZE) * (height // BLOCK_SIZE)
    max_text_bytes = max(0, (capacity_bits - HEADER_BITS) // 8)
    return Capacity(width, height, capacity_bits, max_text_bytes)


def image_file_capacity(path: str | Path) -> Capacity:
    with Image.open(path) as image:
        return image_capacity(*image.size)


def embed_watermark(
    input_path: str | Path,
    output_path: str | Path,
    message: str,
    key: str = "",
    strength: float = 28.0,
    progress_callback: ProgressCallback | None = None,
) -> EmbedResult:
    """Embed a text watermark into an image and save the result."""

    input_path = Path(input_path)
    output_path = Path(output_path)
    payload = message.encode("utf-8")
    if len(payload) > 65535:
        raise WatermarkError("水印文本太长，最多支持 65535 字节。")

    bits = _bytes_to_bits(MAGIC + len(payload).to_bytes(2, "big") + payload)

    with Image.open(input_path) as source:
        rgba_alpha = None
        if source.mode in {"RGBA", "LA"} or "transparency" in source.info:
            rgba = source.convert("RGBA")
            rgba_alpha = rgba.getchannel("A")
            rgb = rgba.convert("RGB")
        else:
            rgb = source.convert("RGB")

        width, height = rgb.size
        capacity = image_capacity(width, height)
        if capacity.capacity_bits < HEADER_BITS:
            raise WatermarkError("图片太小，至少需要 8x48 个可用频域块。")
        if len(bits) > capacity.capacity_bits:
            raise WatermarkError(
                f"图片容量不足：最多约 {capacity.max_text_bytes} 字节，"
                f"当前水印为 {len(payload)} 字节。"
            )

        y_channel, cb_channel, cr_channel = rgb.convert("YCbCr").split()
        pixels = y_channel.load()
        blocks = _shuffled_blocks(width, height, key)

        total = len(bits)
        strength = max(4.0, min(float(strength), 100.0))
        for index, bit in enumerate(bits):
            bx, by = blocks[index]
            block = _read_block(pixels, bx, by)
            coeffs = _dct_8x8(block)
            _write_bit(coeffs, bit, strength)
            updated = _idct_8x8(coeffs)
            _write_block(pixels, bx, by, updated)
            if progress_callback and (index % 16 == 0 or index + 1 == total):
                progress_callback(index + 1, total)

        watermarked = Image.merge("YCbCr", (y_channel, cb_channel, cr_channel)).convert("RGB")
        if rgba_alpha is not None and output_path.suffix.lower() not in {".jpg", ".jpeg"}:
            watermarked.putalpha(rgba_alpha)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs = {}
        if output_path.suffix.lower() in {".jpg", ".jpeg"}:
            save_kwargs = {"quality": 95, "subsampling": 0}
        watermarked.save(output_path, **save_kwargs)

    return EmbedResult(output_path, len(payload), len(bits), capacity.capacity_bits)


def extract_watermark(
    input_path: str | Path,
    key: str = "",
    progress_callback: ProgressCallback | None = None,
) -> ExtractResult:
    """Extract a text watermark from an image."""

    with Image.open(input_path) as source:
        rgb = source.convert("RGB")
        width, height = rgb.size
        capacity = image_capacity(width, height)
        if capacity.capacity_bits < HEADER_BITS:
            raise WatermarkError("图片太小，无法包含本工具的频域水印。")

        y_channel = rgb.convert("YCbCr").split()[0]
        pixels = y_channel.load()
        blocks = _shuffled_blocks(width, height, key)

        header_bits = _extract_bits(pixels, blocks, 0, HEADER_BITS)
        header = _bits_to_bytes(header_bits)
        if header[: len(MAGIC)] != MAGIC:
            raise WatermarkError("没有检测到本工具写入的水印，或密钥不正确。")

        payload_len = int.from_bytes(header[len(MAGIC) : HEADER_BYTES], "big")
        total_bits = HEADER_BITS + payload_len * 8
        if total_bits > capacity.capacity_bits:
            raise WatermarkError("检测到的水印长度超出图片容量，可能密钥不正确或图片被严重压缩。")

        if progress_callback:
            progress_callback(HEADER_BITS, total_bits)
        payload_bits = _extract_bits(
            pixels,
            blocks,
            HEADER_BITS,
            payload_len * 8,
            progress_callback=progress_callback,
            total_bits=total_bits,
        )
        payload = _bits_to_bytes(payload_bits)
        message = payload.decode("utf-8", errors="replace")
        return ExtractResult(message, len(payload), total_bits, capacity.capacity_bits)


def _bytes_to_bits(data: bytes) -> list[int]:
    bits: list[int] = []
    for byte in data:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)
    return bits


def _bits_to_bytes(bits: Iterable[int]) -> bytes:
    values = list(bits)
    if len(values) % 8 != 0:
        raise WatermarkError("内部错误：位序列长度不是 8 的倍数。")
    data = bytearray()
    for offset in range(0, len(values), 8):
        byte = 0
        for bit in values[offset : offset + 8]:
            byte = (byte << 1) | int(bit)
        data.append(byte)
    return bytes(data)


def _shuffled_blocks(width: int, height: int, key: str) -> list[tuple[int, int]]:
    blocks = [
        (block_x, block_y)
        for block_y in range(height // BLOCK_SIZE)
        for block_x in range(width // BLOCK_SIZE)
    ]
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:16], "big")
    rng = random.Random(seed)
    rng.shuffle(blocks)
    return blocks


def _extract_bits(
    pixels,
    blocks: list[tuple[int, int]],
    start: int,
    count: int,
    progress_callback: ProgressCallback | None = None,
    total_bits: int | None = None,
) -> list[int]:
    bits: list[int] = []
    end = start + count
    for index in range(start, end):
        bx, by = blocks[index]
        block = _read_block(pixels, bx, by)
        coeffs = _dct_8x8(block)
        bits.append(_read_bit(coeffs))
        done = index + 1
        if progress_callback and total_bits and (done % 16 == 0 or done == total_bits):
            progress_callback(done, total_bits)
    return bits


_BASIS = [
    [
        (math.sqrt(1 / 8) if freq == 0 else math.sqrt(2 / 8))
        * math.cos(((2 * pos + 1) * freq * math.pi) / 16)
        for pos in range(BLOCK_SIZE)
    ]
    for freq in range(BLOCK_SIZE)
]


def _dct_8x8(block: list[list[int]]) -> list[list[float]]:
    temp = [[0.0] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]
    for y in range(BLOCK_SIZE):
        row = block[y]
        for u in range(BLOCK_SIZE):
            basis_u = _BASIS[u]
            temp[y][u] = sum(row[x] * basis_u[x] for x in range(BLOCK_SIZE))

    coeffs = [[0.0] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]
    for v in range(BLOCK_SIZE):
        basis_v = _BASIS[v]
        for u in range(BLOCK_SIZE):
            coeffs[v][u] = sum(temp[y][u] * basis_v[y] for y in range(BLOCK_SIZE))
    return coeffs


def _idct_8x8(coeffs: list[list[float]]) -> list[list[int]]:
    temp = [[0.0] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]
    for v in range(BLOCK_SIZE):
        row = coeffs[v]
        for x in range(BLOCK_SIZE):
            temp[v][x] = sum(row[u] * _BASIS[u][x] for u in range(BLOCK_SIZE))

    block = [[0] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]
    for y in range(BLOCK_SIZE):
        for x in range(BLOCK_SIZE):
            value = sum(temp[v][x] * _BASIS[v][y] for v in range(BLOCK_SIZE))
            block[y][x] = max(0, min(255, int(round(value))))
    return block


def _read_block(pixels, block_x: int, block_y: int) -> list[list[int]]:
    x0 = block_x * BLOCK_SIZE
    y0 = block_y * BLOCK_SIZE
    return [
        [int(pixels[x0 + x, y0 + y]) for x in range(BLOCK_SIZE)]
        for y in range(BLOCK_SIZE)
    ]


def _write_block(pixels, block_x: int, block_y: int, block: list[list[int]]) -> None:
    x0 = block_x * BLOCK_SIZE
    y0 = block_y * BLOCK_SIZE
    for y in range(BLOCK_SIZE):
        for x in range(BLOCK_SIZE):
            pixels[x0 + x, y0 + y] = block[y][x]


def _write_bit(coeffs: list[list[float]], bit: int, strength: float) -> None:
    ay, ax = COEFF_A
    by, bx = COEFF_B
    average = (coeffs[ay][ax] + coeffs[by][bx]) / 2.0
    half_gap = strength / 2.0
    if bit:
        coeffs[ay][ax] = average + half_gap
        coeffs[by][bx] = average - half_gap
    else:
        coeffs[ay][ax] = average - half_gap
        coeffs[by][bx] = average + half_gap


def _read_bit(coeffs: list[list[float]]) -> int:
    ay, ax = COEFF_A
    by, bx = COEFF_B
    return 1 if coeffs[ay][ax] > coeffs[by][bx] else 0

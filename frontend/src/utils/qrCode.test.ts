import { describe, expect, it } from 'vitest';

import { encodeQrCode, qrCodeSvgPath } from './qrCode';

/** Reads the modules back out of the zigzag, undoing the mask. */
function readCodewords(
  modules: boolean[][],
  reserved: boolean[][],
  mask: number
): number[] {
  const size = modules.length;
  const bits: number[] = [];
  let upward = true;
  for (let right = size - 1; right >= 1; right -= 2) {
    const rightCol = right <= 6 ? right - 1 : right;
    for (let step = 0; step < size; step += 1) {
      const row = upward ? size - 1 - step : step;
      for (let c = 0; c < 2; c += 1) {
        const col = rightCol - c;
        if (reserved[row]![col]!) continue;
        const value = modules[row]![col]!;
        bits.push(maskAt(mask, row, col) ? (value ? 0 : 1) : value ? 1 : 0);
      }
    }
    upward = !upward;
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j += 1) byte = (byte << 1) | bits[i + j]!;
    bytes.push(byte);
  }
  return bytes;
}

/** The same mask functions the encoder uses, restated so the test is a check. */
function maskAt(pattern: number, row: number, col: number): boolean {
  switch (pattern) {
    case 0:
      return (row + col) % 2 === 0;
    case 1:
      return row % 2 === 0;
    case 2:
      return col % 3 === 0;
    case 3:
      return (row + col) % 3 === 0;
    case 4:
      return (Math.floor(row / 2) + Math.floor(col / 3)) % 2 === 0;
    case 5:
      return ((row * col) % 2) + ((row * col) % 3) === 0;
    case 6:
      return (((row * col) % 2) + ((row * col) % 3)) % 2 === 0;
    default:
      return (((row + col) % 2) + ((row * col) % 3)) % 2 === 0;
  }
}

/** Rebuilds the function pattern map for a version, to know what is data. */
function reservedFor(size: number, version: number): boolean[][] {
  const reserved: boolean[][] = Array.from({ length: size }, () =>
    new Array<boolean>(size).fill(false)
  );
  const finder = (row: number, col: number) => {
    for (let r = -1; r <= 7; r += 1) {
      for (let c = -1; c <= 7; c += 1) {
        const rr = row + r;
        const cc = col + c;
        if (rr < 0 || rr >= size || cc < 0 || cc >= size) continue;
        reserved[rr]![cc] = true;
      }
    }
  };
  finder(0, 0);
  finder(0, size - 7);
  finder(size - 7, 0);

  const centresByVersion: readonly (readonly number[])[] = [
    [],
    [6, 18],
    [6, 22],
    [6, 26],
    [6, 30],
    [6, 34],
    [6, 22, 38],
    [6, 24, 42],
    [6, 26, 46],
    [6, 28, 50],
  ];
  const centres = centresByVersion[version - 1]!;
  for (const row of centres) {
    for (const col of centres) {
      const nearFinder =
        (row <= 8 && col <= 8) ||
        (row <= 8 && col >= size - 9) ||
        (row >= size - 9 && col <= 8);
      if (nearFinder) continue;
      for (let r = -2; r <= 2; r += 1) {
        for (let c = -2; c <= 2; c += 1) {
          reserved[row + r]![col + c] = true;
        }
      }
    }
  }
  for (let i = 8; i < size - 8; i += 1) {
    reserved[6]![i] = true;
    reserved[i]![6] = true;
  }
  for (let i = 0; i < 9; i += 1) {
    reserved[8]![i] = true;
    reserved[i]![8] = true;
  }
  for (let i = 0; i < 8; i += 1) {
    reserved[8]![size - 1 - i] = true;
    reserved[size - 1 - i]![8] = true;
  }
  reserved[size - 8]![8] = true;
  if (version >= 7) {
    for (let i = 0; i < 18; i += 1) {
      const row = Math.floor(i / 3);
      const col = size - 11 + (i % 3);
      reserved[row]![col] = true;
      reserved[col]![row] = true;
    }
  }
  return reserved;
}

/**
 * Undoes the block interleaving, returning the data codewords in order.
 *
 * Spelled out here rather than shared with the encoder, so a wrong order in the
 * encoder cannot be cancelled out by the same mistake in the check.
 */
function deinterleave(stream: number[], version: number): number[] {
  const specs: readonly (readonly [number, number, number, number])[] = [
    [16, 10, 1, 0],
    [28, 16, 1, 0],
    [44, 26, 1, 0],
    [64, 18, 2, 0],
    [86, 24, 2, 0],
    [108, 16, 4, 0],
    [124, 18, 4, 0],
    [154, 22, 2, 2],
    [182, 22, 3, 2],
    [216, 26, 4, 1],
  ];
  const [totalData, , group1Blocks, group2Blocks] = specs[version - 1]!;
  const totalBlocks = group1Blocks + group2Blocks;
  const group1Size = Math.floor(totalData / totalBlocks);
  const sizes = Array.from({ length: totalBlocks }, (_, i) =>
    i < group1Blocks ? group1Size : group1Size + 1
  );

  const blocks: number[][] = sizes.map(() => []);
  let at = 0;
  const longest = Math.max(...sizes);
  for (let i = 0; i < longest; i += 1) {
    for (let b = 0; b < totalBlocks; b += 1) {
      if (i < sizes[b]!) blocks[b]!.push(stream[at++]!);
    }
  }
  return blocks.flat();
}

/** Recovers the mask from the format information, then the payload. */
function decodePayload(matrix: { size: number; modules: boolean[][] }): string {
  const { size, modules } = matrix;
  const version = (size - 17) / 4;

  let raw = 0;
  for (let i = 0; i < 15; i += 1) {
    let dark: boolean;
    if (i < 6) dark = modules[i]![8]!;
    else if (i < 8) dark = modules[i + 1]![8]!;
    else dark = modules[size - 15 + i]![8]!;
    if (dark) raw |= 1 << i;
  }
  const unmasked = raw ^ 0b101010000010010;
  const mask = (unmasked >>> 10) & 0b111;

  const interleaved = readCodewords(modules, reservedFor(size, version), mask);
  const codewords = deinterleave(interleaved, version);
  const mode = (codewords[0]! >>> 4) & 0b1111;
  expect(mode).toBe(0b0100);
  const countBits = version <= 9 ? 8 : 16;

  const bits: number[] = [];
  for (const byte of codewords) {
    for (let i = 7; i >= 0; i -= 1) bits.push((byte >>> i) & 1);
  }
  let at = 4;
  let length = 0;
  for (let i = 0; i < countBits; i += 1) length = (length << 1) | bits[at++]!;

  const out: number[] = [];
  for (let i = 0; i < length; i += 1) {
    let byte = 0;
    for (let j = 0; j < 8; j += 1) byte = (byte << 1) | bits[at++]!;
    out.push(byte);
  }
  return new TextDecoder().decode(new Uint8Array(out));
}

describe('encodeQrCode', () => {
  const uri =
    'otpauth://totp/WebbPulse%20Portfolio:tyler@webbpulse.com?secret=JBSWY3DPEHPK3PXP&issuer=WebbPulse%20Portfolio&algorithm=SHA1&digits=6&period=30';

  it('produces a symbol whose size matches its version', () => {
    const { size } = encodeQrCode(uri);
    expect((size - 17) % 4).toBe(0);
    const version = (size - 17) / 4;
    expect(version).toBeGreaterThanOrEqual(1);
    expect(version).toBeLessThanOrEqual(10);
  });

  it('places the three finder patterns and their separators', () => {
    const { size, modules } = encodeQrCode(uri);
    for (const [row, col] of [
      [0, 0],
      [0, size - 7],
      [size - 7, 0],
    ] as const) {
      expect(modules[row]![col]).toBe(true);
      expect(modules[row + 1]![col + 1]).toBe(false);
      expect(modules[row + 3]![col + 3]).toBe(true);
      expect(modules[row + 6]![col + 6]).toBe(true);
    }
  });

  it('lays down the alternating timing patterns', () => {
    const { size, modules } = encodeQrCode(uri);
    for (let i = 8; i < size - 8; i += 1) {
      expect(modules[6]![i]).toBe(i % 2 === 0);
      expect(modules[i]![6]).toBe(i % 2 === 0);
    }
  });

  it('round trips the provisioning URI back out of the data region', () => {
    expect(decodePayload(encodeQrCode(uri))).toBe(uri);
  });

  it('round trips a short value, which lands on a smaller version', () => {
    const short = 'otpauth://totp/a?secret=JBSWY3DPEHPK3PXP';
    const matrix = encodeQrCode(short);
    expect(decodePayload(matrix)).toBe(short);
  });

  it('refuses a value larger than a version 10 symbol holds', () => {
    expect(() => encodeQrCode('x'.repeat(400))).toThrow(/more than a version/i);
  });
});

describe('qrCodeSvgPath', () => {
  it('returns a path and a viewBox with the four module quiet zone', () => {
    const { path, viewBox, size } = qrCodeSvgPath('otpauth://totp/a?secret=JB');
    const matrix = encodeQrCode('otpauth://totp/a?secret=JB');
    expect(size).toBe(matrix.size + 8);
    expect(viewBox).toBe(`0 0 ${size} ${size}`);
    expect(path.startsWith('M')).toBe(true);
    const dark = matrix.modules.flat().filter(Boolean).length;
    expect(path.match(/M/g)?.length).toBe(dark);
    expect(path).not.toContain('M0 0h');
  });
});

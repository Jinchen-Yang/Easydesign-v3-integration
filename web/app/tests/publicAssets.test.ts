import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import reference from '../src/demo/structure-reference.json';

/**
 * 豆豆（看板娘）与演示结构依赖 public/ 下的静态资源。阶段 3 迁移时这批
 * 资源没有跟着搬过来，而 RabbitArt 有三级降级（WebGL 纹理 → <img> →
 * emoji 🐰），所以资源缺失不会报错、测试也曾全绿——界面上只是悄悄退化
 * 成一个 emoji。这里把「资源必须存在」固化成断言，避免再次静默丢失。
 */

const PUBLIC = join(__dirname, '..', 'public');

/** RabbitArt 的 WebGL 纹理：缺了就只剩 emoji 兜底。 */
const TEXTURE = 'mascot/rabbit/rabbit-mascot.png';

/** 豆豆相册的七张原图（RabbitMascot 的 PICTURES）。 */
const GALLERY = [
  '01-welcome', '02-discover', '03-design', '04-analyze',
  '05-explore', '06-easydesign', '07-guide',
].map((name) => `mascot/rabbit/originals/${name}.jpg`);

describe('public 静态资源', () => {
  it('豆豆的 WebGL 纹理存在且是真实 PNG', () => {
    const file = join(PUBLIC, TEXTURE);
    expect(existsSync(file), `${TEXTURE} 缺失：豆豆会退化成 emoji`).toBe(true);
    // PNG magic number，防止占位空文件混过断言。
    expect([...readFileSync(file).subarray(0, 4)]).toEqual([0x89, 0x50, 0x4e, 0x47]);
  });

  it('豆豆相册七张原图齐全', () => {
    for (const picture of GALLERY) {
      expect(existsSync(join(PUBLIC, picture)), `${picture} 缺失`).toBe(true);
    }
  });

  it('演示结构文件存在，且路径能在 /app/ 基路径下解析', () => {
    // localUrl 是根相对（/structures/…）；MolecularViewer 用 BASE_URL 前缀
    // 解析它，否则在 /app/ 部署下本地副本必然 404、每次都回落到 RCSB。
    expect(reference.localUrl.startsWith('/')).toBe(true);
    const relative = reference.localUrl.replace(/^\//, '');
    expect(existsSync(join(PUBLIC, relative)), `${relative} 缺失`).toBe(true);
  });

  it('favicon 存在', () => {
    expect(existsSync(join(PUBLIC, 'favicon.svg'))).toBe(true);
  });
});

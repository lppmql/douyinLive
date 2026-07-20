/**
 * 从后端 OpenAPI schema 生成前端 TypeScript 类型定义。
 *
 * 本地开发（需要后端在 localhost:8000 运行）:
 *   cd frontend && pnpm gen-api
 *
 * 本地开发 + 检查是否与 git 一致:
 *   npx tsx scripts/generate-api-types.ts --check
 *
 * CI 模式（从导出的 JSON 文件读取）:
 *   npx tsx scripts/generate-api-types.ts /tmp/openapi.json --check
 */

import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const ROOT = resolve(import.meta.dirname, '..');
const OUTPUT = resolve(ROOT, 'src/typings/api/generated.d.ts');

function run(cmd: string, cwd?: string) {
  execSync(cmd, {
    cwd: cwd || ROOT,
    stdio: 'inherit',
  });
}

async function main() {
  const args = process.argv.slice(2);
  const isCheck = args.includes('--check');
  const filePath = args.find((a) => a.endsWith('.json'));

  const source = filePath || process.env.OPENAPI_URL || 'http://localhost:8000/openapi.json';

  console.log(`🔍 从 ${source} 生成 API 类型...`);

  // openapi-typescript 支持 URL 和本地文件路径
  run(`npx openapi-typescript ${source} -o ${OUTPUT}`);

  if (!existsSync(OUTPUT)) {
    console.error('❌ 类型文件未生成！');
    process.exit(1);
  }

  console.log(`✅ 已生成: ${OUTPUT}`);

  if (isCheck) {
    try {
      run('git diff --exit-code -- src/typings/api/generated.d.ts');
      console.log('✅ API 类型与后端 schema 一致，检查通过。');
    } catch {
      console.error('');
      console.error('❌ API 类型不同步！后端 schema 与已提交的 generated.d.ts 不一致。');
      console.error('   请本地运行: cd frontend && pnpm gen-api');
      console.error('   然后提交更新后的 src/typings/api/generated.d.ts');
      process.exit(1);
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

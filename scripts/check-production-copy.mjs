import { readFile, readdir } from 'node:fs/promises';
import { extname, relative } from 'node:path';

const root = new URL('../apps/web-v32/', import.meta.url);
const allowedExtensions = new Set(['.html', '.js', '.css']);
const forbiddenPatterns = [
  { name: '连续问号乱码', pattern: /\?{3,}|[>'"\x60]\?{2}[<'"\x60]/g },
  { name: '常见中文乱码', pattern: /[鍙璇绠钀鏅绉妯闂锛銆]/g },
  { name: '演示或占位文案', pattern: /运行演示|使用演示|演示运行|演示数据|模拟数据|示例数据|样例数据|占位|生产原型/gi },
  { name: '前端模拟实现标记', pattern: /\b(?:demo|mock)\b/gi },
];

async function collect(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const target = new URL(entry.name + (entry.isDirectory() ? '/' : ''), directory);
    if (entry.isDirectory()) files.push(...await collect(target));
    else if (allowedExtensions.has(extname(entry.name))) files.push(target);
  }
  return files;
}

const findings = [];
for (const file of await collect(root)) {
  const source = await readFile(file, 'utf8');
  const lines = source.split(/\r?\n/);
  for (const item of forbiddenPatterns) {
    lines.forEach((line, index) => {
      item.pattern.lastIndex = 0;
      if (item.pattern.test(line)) {
        const path = relative(new URL('../', root).pathname, file.pathname);
        findings.push(path + ':' + (index + 1) + ' ' + item.name + ': ' + line.trim());
      }
    });
  }
}

if (findings.length) {
  console.error('Production copy validation failed:\n' + findings.join('\n'));
  process.exit(1);
}

console.log('Production copy validation passed.');

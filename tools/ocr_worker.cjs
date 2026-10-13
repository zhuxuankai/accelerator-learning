// tesseract.js OCR worker：读图片清单，输出 UTF-8 JSON 文件（避免控制台编码问题）
const fs = require('fs');
const path = require('path');
const { createWorker } = require('tesseract.js');

async function main() {
  const [, , langPath, cacheRoot, listPath, outPath, workersArg] = process.argv;
  const images = fs.readFileSync(listPath, 'utf8').split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  const n = Math.max(1, Math.min(6, parseInt(workersArg || '3', 10)));
  if (images.length === 0) {
    fs.writeFileSync(outPath, '[]', 'utf8');
    return;
  }
  const pool = [];
  for (let i = 0; i < n; i++) {
    const cachePath = path.join(cacheRoot, 'w' + i);
    fs.mkdirSync(cachePath, { recursive: true });
    // gzip:false —— 使用已解压的 <lang>.traineddata，避免联网
    pool.push(await createWorker('chi_sim+eng', 1, { langPath, cachePath, gzip: false }));
  }
  const results = new Array(images.length);
  let next = 0;
  async function run(slot) {
    while (true) {
      const i = next++;
      if (i >= images.length) break;
      const file = images[i];
      try {
        const { data } = await pool[slot].recognize(file);
        results[i] = { file: path.basename(file), text: (data.text || '').replace(/\u0000/g, ''), confidence: data.confidence || 0 };
      } catch (err) {
        results[i] = { file: path.basename(file), text: '', confidence: 0, error: String(err && err.message || err) };
      }
    }
  }
  await Promise.all(Array.from({ length: n }, (_, i) => run(i)));
  for (const w of pool) await w.terminate();
  fs.writeFileSync(outPath, JSON.stringify(results), 'utf8');
}

main().catch(err => {
  console.error('WORKER_ERR', err && err.message);
  process.exit(1);
});

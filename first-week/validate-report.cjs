const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('index.html', 'utf8');
const start = html.indexOf('<script>') + '<script>'.length;
const end = html.lastIndexOf('</script>');
if (start < '<script>'.length || end < start) throw new Error('Inline script missing');
const source = html.slice(start, end);
new vm.Script(source);

const ids = Array.from(html.matchAll(/id="([^"]+)"/g), match => match[1]);
const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
if (duplicates.length) throw new Error(`Duplicate ids: ${duplicates.join(', ')}`);

console.log(`JS_OK ${source.length}`);
console.log(`IDS_OK ${ids.length}`);

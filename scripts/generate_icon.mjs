// Deterministically rasterize the editable SVG into macOS asset representations.
// Run with Node and sharp installed (NODE_PATH may point at a shared tool runtime).
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const sharp=require('sharp');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const source=path.join(root,'resources/branding/cornhole-biomechanics-icon.svg');
const iconset=path.join(root,'resources/branding/AppIcon.iconset');
const assets=path.join(root,'app/CornholeBiomechanics/Assets.xcassets/AppIcon.appiconset');
await fs.mkdir(iconset,{recursive:true});await fs.mkdir(assets,{recursive:true});
const images=[];
for(const size of [16,32,128,256,512]){
 for(const scale of [1,2]){
  const filename=`icon_${size}x${size}${scale===2?'@2x':''}.png`;
  const png=await sharp(source).resize(size*scale,size*scale).png().toBuffer();
  await fs.writeFile(path.join(iconset,filename),png);await fs.writeFile(path.join(assets,filename),png);
  images.push({filename,idiom:'mac',size:`${size}x${size}`,scale:`${scale}x`});
 }
}
await fs.writeFile(path.join(assets,'Contents.json'),JSON.stringify({images,info:{author:'Cornhole Biomechanics Lab',version:1}},null,2)+'\n');
await fs.writeFile(path.join(path.dirname(assets),'Contents.json'),JSON.stringify({info:{author:'Cornhole Biomechanics Lab',version:1}})+'\n');

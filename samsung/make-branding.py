"""Rasterise existing channel wordmarks for the Samsung's old image renderer."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import cairosvg
import io
root=Path(__file__).resolve().parent/'widget'/'images'
(root/'brands').mkdir(parents=True,exist_ok=True);(root/'channels').mkdir(exist_ok=True)
fontroot=Path(__file__).resolve().parent/'widget'/'fonts'
font=ImageFont.truetype(str(fontroot/'LiberationSans-Bold.ttf'),34)
for key,label,color in [('bbc','BBC iPlayer','#ff5f9f'),('channel4','Channel 4','#b9ff66'),('u','U','#f9f9fc')]:
 if key in ('bbc','channel4','u') and (root/'brands'/(key+'.png')).exists():continue
 box=font.getbbox(label);im=Image.new('RGBA',(box[2]+10,48));d=ImageDraw.Draw(im);d.text((4,0),label,font=font,fill=color);im.save(root/'brands'/(key+'.png'))
for key in ['bbcone','bbctwo','bbcfour','bbcnews']:
 source=Path('/home/jhewes/tv-favourites/artwork')/(key+'.svg')
 data=cairosvg.svg2png(bytestring=source.read_bytes(),output_width=1280,output_height=720)
 im=Image.open(io.BytesIO(data)).convert('RGB')
 d=ImageDraw.Draw(im);f=ImageFont.truetype(str(fontroot/'LiberationSans-Bold.ttf'),36)
 for i,char in enumerate('BBC'):
  x=556+i*59;d.rectangle((x,103,x+48,151),fill='white');d.text((x+12,104),char,font=f,fill='#151515')
 im.save(root/'channels'/(key+'.png'))
print('Generated 4 live-channel wordmark cards and 3 provider wordmarks.')
for code,key in [('C4','channel4'),('E4','e4'),('M4','more4'),('F4','film4'),('4S','4seven')]:
 source=Path('/home/jhewes/tv-favourites/artwork')/('live_channel4_'+code+'.svg')
 if source.exists():
  cairosvg.svg2png(bytestring=source.read_bytes(),write_to=str(root/'channels'/(key+'.png')),output_width=1280,output_height=720)

"""Run on the Pi as jhewes. Generates one short-lived, single-use pairing code."""
import hashlib,json,secrets,time
from pathlib import Path
root=Path('/home/jhewes/tv-favourites-private/appletv');root.mkdir(parents=True,mode=0o700,exist_ok=True)
code=''.join(str(secrets.randbelow(10)) for _ in range(8))
path=root/'pairing.json';tmp=path.with_suffix('.tmp')
tmp.write_text(json.dumps({'hash':hashlib.sha256(code.encode()).hexdigest(),'expires':time.time()+600}));tmp.chmod(0o600);tmp.replace(path)
print('Apple TV pairing code: '+code[:4]+' '+code[4:]+' (valid for 10 minutes)')

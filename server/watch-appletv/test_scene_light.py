import copy,math,unittest
from scene_light import SceneLight
class Lamp(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.now=100.;self.state={'state':'on','attributes':{'brightness':82,'hs_color':[240,60],'color_mode':'hs','supported_color_modes':['hs']}};self.calls=[]
  async def request(path,data=None):
   if data is None:return copy.deepcopy(self.state)
   self.calls.append((path,data))
   if path.endswith('turn_off'):self.state['state']='off'
   else:
    self.state['state']='on'
    for key in ('brightness','hs_color','xy_color','color_temp_kelvin'):
     if key in data:self.state['attributes'][key]=data[key]
   return []
  self.lamp=SceneLight('light.behind_tv','http://unused','',clock=lambda:self.now,request=request)
 async def test_hue_max_saturation_preserves_brightness_and_restores(self):
  await self.lamp.colour('a',30)
  self.assertEqual(self.calls[0][1]['hs_color'],[30,100]);self.assertNotIn('brightness',self.calls[0][1]);self.assertEqual(self.state['attributes']['brightness'],82)
  await self.lamp.restore('a');self.assertEqual(self.state['attributes']['hs_color'],[240,60]);self.assertEqual(self.state['attributes']['brightness'],82)
 async def test_white_for_neutral_does_not_dim(self):
  await self.lamp.colour('a',120,True);self.assertEqual(self.calls[0][1]['hs_color'],[120,0]);self.assertNotIn('brightness',self.calls[0][1])
  self.state['attributes']['hs_color']=[0,0];await self.lamp.restore('a');self.assertEqual(self.state['attributes']['hs_color'],[240,60])
 async def test_hysteresis_and_heartbeat_lease(self):
  await self.lamp.colour('a',359);self.now+=2;await self.lamp.colour('a',1);self.assertEqual(len(self.calls),1)
  self.now+=10;await self.lamp.expire();self.assertTrue(self.lamp.status()['active'])
  self.now+=3;await self.lamp.expire();self.assertFalse(self.lamp.status()['active'])
 async def test_manual_override_yields_without_restoring(self):
  await self.lamp.colour('a',30);self.state['attributes']['hs_color']=[200,50];self.now+=6
  await self.lamp.colour('a',40);await self.lamp.colour('a',80);await self.lamp.restore('a')
  self.assertEqual(len(self.calls),1);self.assertEqual(self.state['attributes']['hs_color'],[200,50])
 async def test_other_ticket_cannot_take_over_or_restore(self):
  await self.lamp.colour('a',30);self.now+=2;await self.lamp.colour('b',180);await self.lamp.restore('b');self.assertEqual(len(self.calls),1);self.assertEqual(self.lamp.owner,'a')
 async def test_initially_off_restores_off(self):
  self.state['state']='off';await self.lamp.colour('a',30);await self.lamp.restore('a');self.assertEqual(self.state['state'],'off')
 async def test_validation_and_disabled_do_not_touch_light(self):
  for value in [True,'red',None,float('nan'),float('inf'),-1,361]:
   with self.assertRaises(ValueError):await self.lamp.colour('a',value)
  with self.assertRaises(ValueError):await self.lamp.colour('a',30,'yes')
  self.assertEqual(self.calls,[]);self.lamp.entity=None;await self.lamp.colour('a',30);self.assertEqual(self.calls,[])

 async def test_calibration_precise_mode_applies_single_degree_changes(self):
  await self.lamp.colour('calibration',220,precise=True);self.now+=0.4
  await self.lamp.colour('calibration',221,precise=True)
  self.assertEqual(len(self.calls),2);self.assertEqual(self.calls[-1][1]['hs_color'],[221,100]);self.assertNotIn('brightness',self.calls[-1][1])

 async def test_ambient_fade_is_three_seconds_and_calibration_stays_responsive(self):
  await self.lamp.colour('a',220)
  self.assertEqual(self.calls[-1][1]['transition'],3.0)
  self.now+=6;await self.lamp.colour('a',240,precise=True)
  self.assertEqual(self.calls[-1][1]['transition'],0.4)
 async def test_own_transition_is_not_mistaken_for_manual_colour_change(self):
  await self.lamp.colour('a',220);self.now+=4;await self.lamp.colour('a',300)
  self.state['attributes']['hs_color']=[240,100];self.now+=2
  await self.lamp.colour('a',310)
  self.assertEqual(self.lamp.owner,'a');self.assertFalse(self.lamp.status()['manual_override'])

 async def test_live_controls_preserve_brightness(self):
  await self.lamp.colour('a',220,saturation=60,transition=8)
  self.assertEqual(self.calls[-1][1]['hs_color'],[220,60])
  self.assertEqual(self.calls[-1][1]['transition'],8)
  self.assertNotIn('brightness',self.calls[-1][1])
  self.now+=1;await self.lamp.colour('a',220,saturation=60,transition=1)
  self.assertEqual(self.calls[-1][1]['transition'],1)
  self.now+=1;await self.lamp.colour('a',220,white=True,saturation=60,transition=1)
  self.assertEqual(self.calls[-1][1]['hs_color'],[220,0])
 async def test_live_control_bounds(self):
  for value in [True,'slow',None,float('nan'),-1,11]:
   with self.assertRaises(ValueError):await self.lamp.colour('a',30,transition=value)
  for value in [True,'max',None,float('nan'),-1,101]:
   with self.assertRaises(ValueError):await self.lamp.colour('a',30,saturation=value)
  self.assertEqual(self.calls,[])

 async def test_brightness_black_recovery_and_restore(self):
  await self.lamp.colour('a',220,saturation=40,brightness=20)
  self.assertEqual(self.calls[-1][1]['brightness'],51)
  self.now+=6;await self.lamp.colour('a',220,brightness=0)
  self.assertTrue(self.calls[-1][0].endswith('turn_off'))
  self.now+=6;await self.lamp.colour('a',220,brightness=60)
  self.assertEqual(self.calls[-1][1]['brightness'],153)
  self.assertEqual(self.lamp.owner,'a')
  self.now+=6;await self.lamp.colour('a',220)
  self.assertEqual(self.calls[-1][1]['brightness'],82)
  self.now+=6;await self.lamp.restore('a')
  self.assertEqual(self.state['attributes']['brightness'],82)
 async def test_restore_after_black(self):
  await self.lamp.colour('a',220,brightness=0)
  self.now+=6;await self.lamp.restore('a')
  self.assertEqual(self.state['state'],'on')
  self.assertEqual(self.state['attributes']['brightness'],82)
 async def test_invalid_brightness(self):
  for value in [True,None,'dark',float('nan'),-2,101]:
   with self.assertRaises(ValueError):await self.lamp.colour('a',30,brightness=value)
  self.assertEqual(self.calls,[])

class GatewayBoundary(unittest.IsolatedAsyncioTestCase):
 async def idle(self):
  import asyncio
  await asyncio.sleep(3600)
 async def asyncSetUp(self):
  import test_server
  await test_server.Tests.asyncSetUp(self)
 async def asyncTearDown(self):
  import test_server
  await test_server.Tests.asyncTearDown(self)
 async def test_requires_pairing_and_ownership(self):
  import test_server,hashlib
  response=await self.client.post('/scene-light',json={'ticket':'other','hue':30});self.assertEqual(response.status,401)
  token=await test_server.Tests.pair(self);headers={'Authorization':'Bearer '+token}
  response=await self.client.post('/scene-light',headers=headers,json={'ticket':'missing','hue':30});self.assertEqual(response.status,404)
  owner=self.gateway.read('devices.json',{})[hashlib.sha256(token.encode()).hexdigest()]
  self.gateway.sessions['a']={'device':owner,'prepared':{},'stream':None,'seen':0}
  response=await self.client.post('/scene-light',headers=headers,json={'ticket':'a','hue':float('nan')});self.assertEqual(response.status,400)
  response=await self.client.post('/scene-light',headers=headers,json={'ticket':'a','hue':30});self.assertEqual(response.status,200);self.assertFalse((await response.json())['configured'])

 async def test_calibration_is_paired_scoped_and_cannot_replace_playback(self):
  import test_server,hashlib
  from unittest.mock import AsyncMock
  token=await test_server.Tests.pair(self);headers={'Authorization':'Bearer '+token}
  request=AsyncMock(return_value={'state':'on','attributes':{'brightness':80,'hs_color':[240,60],'color_mode':'hs','supported_color_modes':['hs']}})
  self.gateway.scene_light=SceneLight('light.behind_tv','http://unused','',request=request)
  response=await self.client.post('/scene-light/calibration',json={'hue':240});self.assertEqual(response.status,401)
  self.gateway.scene_light.owner='active-playback';self.gateway.scene_light.seen=self.gateway.scene_light.clock()
  response=await self.client.post('/scene-light/calibration',headers=headers,json={'hue':240});self.assertEqual(response.status,409);request.assert_not_called()
  self.gateway.scene_light.owner=None
  response=await self.client.post('/scene-light/calibration',headers=headers,json={'hue':240});self.assertEqual(response.status,200)
  owner=self.gateway.scene_light.owner;self.assertTrue(owner.startswith('calibration:'))
  second=await test_server.Tests.pair(self,'87654321')
  response=await self.client.delete('/scene-light/calibration',headers={'Authorization':'Bearer '+second});self.assertEqual(response.status,200);self.assertEqual(self.gateway.scene_light.owner,owner)
  response=await self.client.delete('/scene-light/calibration',headers=headers);self.assertEqual(response.status,200);self.assertIsNone(self.gateway.scene_light.owner)
